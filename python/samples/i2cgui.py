import time
import struct
import sys
import os
import re
import threading
from functools import partial

import wx
import wx.lib.newevent as NE

from i2cdriver import I2CDriver

PingEvent, EVT_PING = NE.NewEvent()

def ping_thr(win):
    while True:
        wx.PostEvent(win, PingEvent())
        time.sleep(1)

class HexTextCtrl(wx.TextCtrl):
    def __init__(self, *args, **kwargs):
        super(HexTextCtrl, self).__init__(*args, **kwargs)
        self.Bind(wx.EVT_TEXT, self.on_text)
    def on_text(self, event):
        event.Skip()
        selection = self.GetSelection()
        value = self.GetValue().upper()
        hex = "0123456789ABCDEF"
        value = "".join([c for c in value if c in hex])
        self.ChangeValue(value)
        self.SetSelection(*selection)

class Frame(wx.Frame):
    def __init__(self):

        self.sd = None

        def widepair(a, b):
            r = wx.BoxSizer(wx.HORIZONTAL)
            r.Add(a, 1, wx.LEFT)
            r.AddStretchSpacer(prop=1)
            r.Add(b, 1, wx.RIGHT)
            return r

        def pair(a, b):
            r = wx.BoxSizer(wx.HORIZONTAL)
            r.Add(a, 1, wx.LEFT)
            r.Add(b, 0, wx.RIGHT)
            return r

        def rpair(a, b):
            r = wx.BoxSizer(wx.HORIZONTAL)
            r.Add(a, 0, wx.LEFT)
            r.Add(b, 1, wx.RIGHT)
            return r

        def label(s):
            return wx.StaticText(self, label = s)

        def hbox(items):
            r = wx.BoxSizer(wx.HORIZONTAL)
            [r.Add(i, 0, wx.EXPAND) for i in items]
            return r

        def hcenter(i):
            r = wx.BoxSizer(wx.HORIZONTAL)
            r.AddStretchSpacer(prop=1)
            r.Add(i, 2, wx.CENTER)
            r.AddStretchSpacer(prop=1)
            return r

        def vbox(items):
            r = wx.BoxSizer(wx.VERTICAL)
            [r.Add(i, 0, wx.EXPAND) for i in items]
            return r

        wx.Frame.__init__(self, None, -1, "I2CDriver")

        self.label_serial = wx.StaticText(self, label = "-", style = wx.ALIGN_RIGHT)
        self.label_voltage = wx.StaticText(self, label = "-", style = wx.ALIGN_RIGHT)
        self.label_current = wx.StaticText(self, label = "-", style = wx.ALIGN_RIGHT)
        self.label_temp = wx.StaticText(self, label = "-", style = wx.ALIGN_RIGHT)
        self.label_speed = wx.StaticText(self, label = "-", style = wx.ALIGN_RIGHT)
        self.label_uptime = wx.StaticText(self, label = "-", style = wx.ALIGN_RIGHT)

        self.dynamic = [
            self.label_voltage,
            self.label_current,
            self.label_temp,
            self.label_speed,
            self.label_uptime
        ]

        self.Bind(EVT_PING, self.refresh)

        self.heat = {i:label("%02X" % i) for i in range(8, 112)}
        [self.hot(i, False) for i in self.heat]
        devgrid = wx.GridSizer(14, 8)
        for i,l in self.heat.items():
            devgrid.Add(l)
        self.hot(0x44, True)

        self.monitor = False
        self.ckM = wx.CheckBox(self, label = "Monitor mode")
        self.ckM.Bind(wx.EVT_CHECKBOX, self.check_m)

        self.allw = [self.ckM]
        [w.Enable(False) for w in self.allw]
        self.devs = self.devices()
        cb = wx.ComboBox(self, choices = sorted(self.devs.keys()), style = wx.CB_READONLY)
        cb.Bind(wx.EVT_COMBOBOX, self.choose_device)
        vb = vbox([
            label(""),
            hcenter(cb),
            label(""),
            hcenter(pair(
                vbox([
                    label("Serial"),
                    label("Voltage"),
                    label("Current"),
                    label("Temp."),
                    label("Speed"),
                    label("Running"),
                ]),
                vbox([
                    self.label_serial,
                    self.label_voltage,
                    self.label_current,
                    self.label_temp,
                    self.label_speed,
                    self.label_uptime,
                ])
            )),

            label(""),
            hcenter(devgrid),
            label(""),
            hcenter(self.ckM),
            label(""),
            ])
        self.SetSizerAndFit(vb)
        self.SetAutoLayout(True)

        if len(self.devs) > 0:
            d1 = min(self.devs)
            self.connect(self.devs[d1])
            cb.SetValue(d1)

        t = threading.Thread(target=ping_thr, args=(self, ))
        t.setDaemon(True)
        t.start()

    def devices(self):
        if sys.platform == 'darwin':
            devdir = "/dev/"
            pattern = "^tty.usbserial-(........)"
        else:
            devdir = "/dev/serial/by-id/"
            pattern = "^usb-FTDI_FT230X_Basic_UART_(........)-"

        if not os.access(devdir, os.R_OK):
            return {}
        devs = os.listdir(devdir)
        def filter(d):
            m = re.match(pattern, d)
            if m:
                return (m.group(1), devdir + d)
        seldev = [filter(d) for d in devs]
        return dict([d for d in seldev if d])

    def connect(self, dev):
        self.sd = I2CDriver(dev)
        [w.Enable(True) for w in self.allw]
        self.refresh(None)

    def refresh(self, e):
        if self.sd and not self.monitor:
            self.sd.getstatus()
            self.label_serial.SetLabel(self.sd.serial)
            self.label_voltage.SetLabel("%.2f V" % self.sd.voltage)
            self.label_current.SetLabel("%d mA" % self.sd.current)
            self.label_temp.SetLabel("%.1f C" % self.sd.temp)
            self.label_speed.SetLabel("%d kHz" % self.sd.speed)
            days = self.sd.uptime // (24 * 3600)
            rem = self.sd.uptime % (24 * 3600)
            hh = rem // 3600
            mm = (rem / 60) % 60
            ss = rem % 60;
            self.label_uptime.SetLabel("%d:%02d:%02d:%02d" % (days, hh, mm, ss))

            devs = self.sd.scan(True)
            for i,l in self.heat.items():
                self.hot(i, i in devs)

    def choose_device(self, e):
        self.connect(self.devs[e.EventObject.GetValue()])

    def check_m(self, e):
        self.monitor = e.EventObject.GetValue()
        self.sd.monitor(self.monitor)
        [d.Enable(not self.monitor) for d in self.dynamic]
        if self.monitor:
            [self.hot(i, False) for i in self.heat]

    def hot(self, i, s):
        l = self.heat[i]
        if s:
            l.SetForegroundColour((0,0,0))
        else:
            l.SetForegroundColour((160,) * 3)

if __name__ == '__main__':
    app = wx.App(0)
    f = Frame()
    f.Show(True)
    app.MainLoop()
