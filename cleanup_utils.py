"""Shared owner cleanup; no I/O, workers or retry loops of its own."""
def recover_owners(owners):
    pending=tuple(owners);errors=[]
    for owner in pending:
        try:owner.close()
        except Exception as exc:errors.append(exc)
    if len(errors)==1:raise errors[0]
    if errors:raise RuntimeError(' · '.join(str(error) for error in errors)) from errors[0]
    return len(pending)

def cleanup_failed_start(owner,original):
    try:owner.close()
    except Exception as cleanup:
        raise RuntimeError(f'{original} · 시작 실패 후 정리도 실패: {cleanup}') from original
