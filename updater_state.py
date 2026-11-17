"""Read-only verification of the official updater registration."""
import json
from driver_state import ps_read

SCRIPT=r'''
$name='nefarius_HidHide_Updater.exe'
$run=@()
foreach ($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Run','HKLM:\Software\Microsoft\Windows\CurrentVersion\Run')) {
 if (Test-Path -LiteralPath $key) {
  $props=Get-ItemProperty -LiteralPath $key
  foreach ($p in $props.PSObject.Properties) {
   if ($p.Name -notlike 'PS*' -and [string]$p.Value -match '(?i)nefarius_HidHide_Updater\.exe(?:"|\s|$)') { $run+=([string]$p.Value) }
  }
 }
}
$tasks=@(Get-ScheduledTask | Where-Object {
 @($_.Actions | Where-Object { [IO.Path]::GetFileName(([string]$_.Execute).Trim('"')) -ieq $name }).Count -gt 0
} | Select-Object TaskName,TaskPath,State)
@{run_count=$run.Count;tasks=$tasks} | ConvertTo-Json -Depth 4 -Compress
'''

class CleanupError(RuntimeError):pass

def validate(state):
    if not isinstance(state,dict) or type(state.get('run_count')) is not int or state['run_count']<0 or not isinstance(state.get('tasks'),list) or any(not isinstance(t,dict) for t in state['tasks']):raise RuntimeError('업데이터 등록 상태 응답 오류')
    return state

def is_off(state):
    state=validate(state)
    return state['run_count']==0 and not state['tasks']

def read_state():
    state=json.loads(ps_read(SCRIPT))
    return validate(state)

def verify(enabled):
    state=read_state()
    runs=state['run_count'];tasks=state['tasks']
    complete=(runs>0 and any(isinstance(t,dict) and str(t.get('State')) in ('Ready','Running','Queued','2','3','4') for t in tasks)) if enabled else is_off(state)
    if not complete:raise RuntimeError('업데이터 자동 실행 등록 결과 미확인 · 시작 프로그램/작업 스케줄러를 확인하세요. 다른 관리자 계정으로 승인했다면 해당 계정 설정도 확인하세요.')
    return '업데이터 자동 실행 '+('등록' if enabled else '해제')+' 재조회 확인 완료'
