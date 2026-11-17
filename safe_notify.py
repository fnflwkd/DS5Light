"""Progress reporting cannot change operation outcomes."""
def notify(callback,text):
    try:callback(text)
    except Exception:pass
