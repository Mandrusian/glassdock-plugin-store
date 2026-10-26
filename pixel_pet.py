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

class PixelPet(PluginBase):
    NAME = 'Pixel Companion'
    TICK = 0.35
    PERMISSIONS = []
    TRANSPARENT = True
    CONFIG = {'accent': {'type': 'color', 'default': '#83b4ff', 'label': 'Accent colour'},
 'name': {'type': 'str', 'default': 'PIX', 'label': 'Companion name'},
 'motion': {'type': 'bool', 'default': True, 'label': 'Enable bounce'}}

    def on_load(self):self.mood=0;self.phase=0;self.moods=['HAPPY','SLEEPY','PLAYFUL']
    def on_tick(self):self.phase+=.19;self.ctx.redraw()
    def render(self,cr,w,h):
        _panel(cr,w,h,self.ctx)
        c=_rgba(self.ctx.cfg('accent'))
        bob=math.sin(self.phase)*h*.045 if self.ctx.cfg('motion') else 0
        _round(cr,w*.23,h*.29+bob,w*.54,h*.45,min(w,h)*.12);_source(cr,c,.92);cr.fill()
        eye=h*.052
        for xx in (.39,.61):
            _round(cr,w*xx-eye/2,h*.43+bob,eye,eye,eye*.10);_source(cr,(.07,.10,.17,1));cr.fill()
        if self.mood==0:
            cr.arc(w*.5,h*.56+bob,min(w,h)*.09,.1,math.pi-.1);_source(cr,(.07,.10,.17,1));cr.set_line_width(max(1,w*.026));cr.stroke()
        elif self.mood==1:
            _text(cr,'z',w*.77,h*.34+bob,min(w,h)*.19,(1,1,1,.88))
        else:
            _round(cr,w*.46,h*.52+bob,w*.08,h*.075,h*.03);_source(cr,(.07,.10,.17,1));cr.fill()
        _text(cr,str(self.ctx.cfg('name'))[:9],w*.5,h*.20,min(w,h)*.13,self.ctx.colors['fg'])
        _text(cr,self.moods[self.mood],w*.5,h*.89,min(w,h)*.105,(1,1,1,.69),False)
    def on_click(self,button):
        self.mood=0 if button==2 else (self.mood+1)%3;self.ctx.redraw();return [str(self.ctx.cfg('name'))+': '+self.moods[self.mood]]
    def tooltip(self):return 'Pixel Companion · click to change mood'
