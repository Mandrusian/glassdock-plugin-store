"""Self-contained GlassDock user plugin. Runs as your user; review before enabling."""
from glassdock.plugin_api import PluginBase
import math
import datetime


def _num(value, fallback=0.0):
    try:
        n = float(value)
        return n if math.isfinite(n) else fallback
    except (TypeError, ValueError, OverflowError):
        return fallback


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, _num(value)))


def _rgba(value, fallback=(0.52, 0.72, 1.0, 1.0)):
    if isinstance(value, (list, tuple)) and len(value) in (3, 4):
        a = tuple(_clamp(x) for x in value)
        return a if len(a) == 4 else a + (1.0,)
    if isinstance(value, str) and value.startswith('#'):
        s = value[1:]
        if len(s) in (3, 4):
            s = ''.join(ch * 2 for ch in s)
        if len(s) in (6, 8):
            try:
                rgb = tuple(int(s[i:i+2], 16) / 255.0 for i in range(0, len(s), 2))
                return rgb if len(rgb) == 4 else rgb + (1.0,)
            except ValueError:
                pass
    return fallback


def _mix(a, b, t):
    t = _clamp(t)
    return tuple(a[i] * (1-t) + b[i] * t for i in range(4))


def _source(cr, color, opacity=1.0):
    r, g, b, a = _rgba(color)
    cr.set_source_rgba(r, g, b, a * _clamp(opacity))


def _round(cr, x, y, w, h, r):
    w, h = max(0.0, w), max(0.0, h)
    r = min(max(0.0, r), w/2, h/2)
    cr.new_sub_path()
    cr.arc(x+w-r, y+r, r, -math.pi/2, 0)
    cr.arc(x+w-r, y+h-r, r, 0, math.pi/2)
    cr.arc(x+r, y+h-r, r, math.pi/2, math.pi)
    cr.arc(x+r, y+r, r, math.pi, 3*math.pi/2)
    cr.close_path()


def _panel(cr, w, h, ctx, alpha=0.64):
    if w <= 1 or h <= 1:
        return
    bg = _rgba(ctx.colors.get('bg', (0.09, 0.10, 0.16, 1)))
    _round(cr, 0.8, 0.8, w-1.6, h-1.6, min(w,h)*0.24)
    _source(cr, bg, alpha)
    cr.fill_preserve()
    _source(cr, ctx.colors.get('fg', (1,1,1,1)), 0.23)
    cr.set_line_width(max(0.7, min(w,h)*0.015))
    cr.stroke()
    cr.move_to(w*0.20, h*0.065)
    cr.line_to(w*0.80, h*0.065)
    _source(cr, (1,1,1,0.18))
    cr.set_line_width(max(0.5,h*.011))
    cr.stroke()


def _text(cr, text, x, y, size, color=(1,1,1,1), weight=True, center=True, limit=24, max_width=None):
    s = str(text).replace('\n', ' ')[:limit]
    cr.select_font_face('Sans', 0, 1 if weight else 0)
    cr.set_font_size(max(1.0, size))
    ext = cr.text_extents(s)
    width_cap = (max(1.0, x*1.72) if center else None) if max_width is None else max(1.0, max_width)
    if width_cap and ext.width > width_cap:
        cr.set_font_size(max(1.0, size*width_cap/max(1.0, ext.width)))
        ext = cr.text_extents(s)
    if center:
        x -= ext.width/2 + ext.x_bearing
    _source(cr, color)
    cr.move_to(x, y)
    cr.show_text(s)


def _ring(cr, x, y, r, value, color, thickness, start=-math.pi/2, span=2*math.pi):
    r = max(0.1, r)
    cr.set_line_width(max(0.6, thickness))
    cr.set_line_cap(1)
    cr.arc(x, y, r, start, start + span)
    _source(cr, (1,1,1,0.12))
    cr.stroke()
    cr.arc(x, y, r, start, start + span * _clamp(value))
    _source(cr, color)
    cr.stroke()


def _bar(cr, x, y, w, h, value, color, horizontal=True):
    _round(cr, x, y, w, h, min(w,h)/2)
    _source(cr, (1,1,1,0.12))
    cr.fill()
    p = _clamp(value)
    if p <= 0:
        return
    if horizontal:
        ww = w*p
        _round(cr, x, y, ww, h, min(ww,h)/2)
    else:
        hh = h*p
        _round(cr, x, y+h-hh, w, hh, min(w,hh)/2)
    _source(cr, color)
    cr.fill()


def _spark(cr, data, x, y, w, h, color, lo=0.0, hi=None):
    if not data:
        return
    values = [_num(v) for v in data]
    upper = max(float(lo)+0.0001, _num(hi, max(values)) if hi is not None else max(values)*1.12)
    if len(values) == 1:
        values = values*2
    cr.new_path()
    for i, val in enumerate(values):
        px = x + w * i/(len(values)-1)
        py = y + h*(1-_clamp((val-lo)/(upper-lo)))
        if i:
            cr.line_to(px, py)
        else:
            cr.move_to(px, py)
    _source(cr, color)
    cr.set_line_width(max(1, min(w,h)*0.055))
    cr.set_line_join(1)
    cr.set_line_cap(1)
    cr.stroke()


def _speed(v):
    v = max(0.0, _num(v))
    for unit in ('B/s','KB/s','MB/s','GB/s','TB/s'):
        if v < 1024 or unit == 'TB/s':
            return ('%.0f ' if v>=100 else '%.1f ') % v + unit
        v /= 1024


def _elapsed(seconds):
    s = max(0, int(_num(seconds)))
    h, r = divmod(s, 3600)
    m, ss = divmod(r, 60)
    return '%d:%02d:%02d' % (h,m,ss) if h else '%02d:%02d' % (m,ss)


def _trail(values, new, limit=30):
    values.append(_num(new))
    if len(values) > limit:
        del values[:-limit]

class ThermalTrail(PluginBase):
    NAME = 'Thermal Trail'
    TICK = 5
    PERMISSIONS = []
    TRANSPARENT = True
    CONFIG = {'accent': {'type': 'color', 'default': '#83b4ff', 'label': 'Accent colour'},
 'floor': {'type': 'int', 'default': 20, 'label': 'Graph floor °C', 'min': 0, 'max': 70},
 'ceiling': {'type': 'int', 'default': 105, 'label': 'Graph ceiling °C', 'min': 70, 'max': 150}}

    def on_load(self): self.history=[];self.temp=None
    def on_tick(self):
        t=self.ctx.stats.temp()
        self.temp=t
        if t is not None:_trail(self.history,t,36)
        self.ctx.redraw()
    def render(self,cr,w,h):
        _panel(cr,w,h,self.ctx)
        _text(cr,'THERMAL',w*.5,h*.23,min(w,h)*.13,(1,1,1,.67),False)
        _text(cr,'--' if self.temp is None else '%.1f°'%_num(self.temp),w*.5,h*.49,min(w,h)*.24,self.ctx.colors['fg'])
        lo=self.ctx.cfg('floor');hi=max(lo+1,self.ctx.cfg('ceiling'))
        _spark(cr,self.history,w*.12,h*.65,w*.76,h*.20,_rgba(self.ctx.cfg('accent')),lo,hi)
    def on_click(self,button):
        if button==2:self.history.clear();self.ctx.redraw();return ['Thermal history cleared']
        return ['Samples: %d (5 s apart)'%len(self.history),'Session peak: %.1f °C'%max(self.history)] if self.history else ['No sensor data yet']
    def tooltip(self):return 'Thermal Trail · %d samples'%len(self.history)
