"""Local edit detection, independent of permission to write a device snapshot."""
def has_pending_edits(panel):
    baseline=getattr(panel,'snapshot',None) or getattr(panel,'edit_baseline',None)
    rows=getattr(panel,'rows',())
    disabled=getattr(panel,'disabled',0xffffffff)
    changed=(tuple(rows)!=baseline.rows or disabled!=baseline.disabled) if baseline else (any(any(row) for row in rows) or disabled!=0xffffffff)
    enabled=getattr(panel,'ps_enabled',None)
    if enabled is not None:
        ps_changed=bool(enabled.get())!=(bool(baseline.ps_shortcut) if baseline else False)
        return bool(changed or ps_changed or getattr(panel,'pending_keyboard',False))
    ps=getattr(panel,'disable_ps',None)
    return bool(changed or (ps is not None and ps.get()) or getattr(panel,'pending_keyboard',False))
