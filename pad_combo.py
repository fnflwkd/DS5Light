"""Explicitly tagged simultaneous pad outputs, stored as native held rows."""
TAG='DS5L:combo:v1'
PAD=('↑','↓','←','→','□','×','○','△','L1','R1','L2','R2','Create','Options','L3','R3')
def tagged(r):return r[19:35].split(b'\0')[0]==TAG.encode()
def valid_group(records):
    from remapping import editable,OUTPUTS
    return (2<=len(records)<=len(PAD) and all(tagged(r) and editable(r) and r[4]==0 and r[5] in (2,6) and not any(r[6:11]) and OUTPUTS[r[17]] in PAD for r in records)
        and len({r[:6] for r in records})==1 and int.from_bytes(records[0][:4],'little').bit_count()==1
        and len({r[17] for r in records})==len(records)
        and not {'↑','↓'}<={OUTPUTS[r[17]] for r in records} and not {'←','→'}<={OUTPUTS[r[17]] for r in records})
def group_indices(rows,chord):return [i for i,r in enumerate(rows) if int.from_bytes(r[:4],'little')==chord and tagged(r)]
def stage(rows,mask,chord,outputs,keep=False):
    from remapping import EMPTY,make_record
    outputs=tuple(dict.fromkeys(outputs))
    if not 2<=len(outputs)<=len(PAD) or any(o not in PAD for o in outputs):raise ValueError('서로 다른 패드 버튼을 2개 이상 입력하세요.')
    if {'↑','↓'}<=set(outputs) or {'←','→'}<=set(outputs):raise ValueError('반대 방향 버튼은 동시에 지정할 수 없습니다.')
    if chord.bit_count()!=1:raise ValueError('키 조합을 실행할 버튼은 한 개를 선택하세요.')
    indices=[i for i,r in enumerate(rows) if int.from_bytes(r[:4],'little')==chord and r!=EMPTY]
    if len(indices)>1 and not valid_group([rows[i] for i in indices]):raise ValueError('기존 중복 리맵을 설정 목록에서 먼저 정리하세요.')
    from remapping import editable
    if any(not editable(rows[i]) for i in indices):raise ValueError('기존 고급 매크로는 보존해야 합니다.')
    slots=indices+[i for i,r in enumerate(rows) if r==EMPTY]
    if len(slots)<len(outputs):raise ValueError('장치 리맵 슬롯이 부족합니다. 출력 버튼마다 한 칸이 필요합니다.')
    result=list(rows)
    for i in indices:result[i]=EMPTY;mask|=1<<i
    for i,output in zip(slots,outputs):result[i]=make_record(chord,output,replace=not keep,label=TAG);mask&=~(1<<i)
    return result,mask
