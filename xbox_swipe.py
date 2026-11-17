"""DualSense USB touch gestures, classified on release; no polling or I/O."""
class Swipe:
    def __init__(self):self.reset()
    def reset(self):self.armed=False;self.contact=None
    def update(self,raw,now):
        if raw is None:return ()
        if len(raw)!=64 or raw[0]!=1:self.reset();return ()
        def point(offset):
            b=raw[offset:offset+4]
            return not bool(b[0]&128),b[0]&127,b[1]|((b[2]&15)<<8),(b[2]>>4)|(b[3]<<4)
        down,ident,x,y=point(33);second,_,sx,sy=point(37)
        if (down and (x>1919 or y>1079)) or (second and (sx>1919 or sy>1079)) or raw[10]&2:
            self.reset();return ()
        if not self.armed:
            if not down:self.armed=True
            return ()
        if down:
            if self.contact is None:self.contact=[ident,x,y,x,y,now,second]
            elif self.contact[0]!=ident:self.reset()
            else:self.contact[3:5]=[x,y];self.contact[6]|=second
            return ()
        c=self.contact;self.contact=None
        if c is None:return ()
        c[6]|=second
        duration=now-c[5]
        if not .04<=duration<=.6:return ()
        dx,dy=c[3]-c[1],c[4]-c[2]
        if abs(dx)>=200 and abs(dx)>abs(dy):direction=3 if dx>0 else 2
        elif abs(dy)>=200 and abs(dy)>abs(dx):direction=1 if dy>0 else 0
        else:return ()
        return (16+direction+(4 if c[1]>959 else 0)+(8 if c[6] else 0),)
