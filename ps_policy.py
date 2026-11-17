"""PS shortcut/remap exclusion; definitions are preserved."""
def ps_rows(rows):
    return sum(1<<i for i,r in enumerate(rows) if int.from_bytes(r[:4],'little')&(1<<16))

def resolve(original,disable_ps,enabled):
    if enabled is not None and type(enabled) is not bool:raise ValueError('PS shortcut setting must be boolean')
    return int(enabled) if enabled is not None else (0 if disable_ps else original)

def write_policy(client,check,old_mask,new_mask,old_ps,new_ps):
    def write(field,payload):
        check();client.studio.control_packet(1,field,payload)
        if bytes(client.field(field)[4:4+len(payload)])!=payload:raise RuntimeError('PS 단축키/리맵 활성 상태 검증 실패')
    if old_ps and not new_ps:write(0x0e,b'\0')
    if old_mask!=new_mask:write(0x6c,new_mask.to_bytes(4,'little'))
    if new_ps and old_ps!=new_ps:write(0x0e,bytes([new_ps]))
