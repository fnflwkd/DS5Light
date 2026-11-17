"""UI-thread task exclusion; no device polling or background worker."""
DRIVER_MUTATIONS=frozenset(('install','driver_install','hide_install','hide_driver_install','uninstall','hide_uninstall','updater_check'))

def device_work_active(app):
    if getattr(getattr(app,'studio_window',None),'busy',False) is True or getattr(getattr(app,'remap_panel',None),'busy',False) is True:return True
    if getattr(getattr(app,'battery',None),'busy',False) is True:return True
    if getattr(getattr(app,'remap_panel',None),'preview_timer',None) is not None:return True
    engine=getattr(app,'engine',None)
    return bool(engine and getattr(engine,'thread',None) and engine.thread.is_alive() is True)

def management_busy(app):
    xbox=getattr(app,'xbox',None)
    if xbox is None:return False
    worker=getattr(xbox,'worker',None)
    return getattr(xbox,'busy',False) is True or getattr(worker,'alive',False) is True and getattr(worker,'phase',None) in ('starting','stopping')

def source_settings_blocked(app):
    worker=getattr(getattr(app,'xbox',None),'worker',None)
    from xbox_settings_job import supported
    if getattr(worker,'alive',False) is True and getattr(worker,'phase',None)=='running' and supported(worker):return False
    if getattr(worker,'source_active',False) is True:return True
    from xbox_remap_session import pending
    return pending()
