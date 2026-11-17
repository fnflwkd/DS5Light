"""Reuse verified engine metadata without starting another HID transaction."""
def sync(panel,guard):
    with guard.lock:
        connection=guard.connection;profile=dict(guard.profile) if guard.profile else None
        identity=dict(guard.identity) if guard.identity else None;ah=guard.ah
    index=panel.device.current()
    matched=connection=='confirmed' and identity and 0<=index<len(panel.paths) and panel.paths[index]==identity.get('path')
    if not matched or profile is None:
        panel.invalidate();return
    if panel.profile!=profile:panel.invalidate()
    panel.show_profile(profile);panel.ah=ah
