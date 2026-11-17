"""Shutdown-only retry of residual game-capture cleanup; no active polling thread."""
import threading
import queue
from tkinter import messagebox
from pathlib import Path
import os
from driver_state import atomic_json

def record_failure(error):
    path=Path(os.environ['LOCALAPPDATA'])/'DS5Light'/'logs'/'shutdown-error.json'
    try:atomic_json(path,{'error':str(error)})
    except OSError:return False
    return True

class CaptureCleanup:
    def __init__(self,temporary=False):self.jobs=queue.Queue();self.busy=False;self.done=False;self.temporary=temporary
    def finish(self,root):
        if self.done:return True
        if not self.busy:
            if self.temporary:
                from temporary_remap import owned_pending,restore_owned
                pending=owned_pending();recover_pending=restore_owned
            else:
                from process_audio import _PENDING,recover_pending
                pending=bool(_PENDING)
            if not pending:self.done=True;return True
            self.busy=True
            def work():
                try:recover_pending();self.jobs.put(None)
                except Exception as exc:self.jobs.put(exc)
            try:threading.Thread(target=work,daemon=True).start()
            except Exception as exc:self.jobs.put(exc)
        try:error=self.jobs.get_nowait()
        except queue.Empty:return False
        self.busy=False
        if error:
            saved=record_failure(error)
            note='오류 기록 저장 완료.' if saved else '오류 기록 저장 실패 · 화면 내용을 별도로 보관하세요.'
            title='리맵 저장·복구 확인 필요' if self.temporary else '게임 오디오 종료 실패'
            detail='재시도: 장치를 연결하고 원래 리맵 복원\n취소: 복구 기록을 남기고 종료. 다음 실행에서 리맵 문제 해결 → 임시 적용 전으로 되돌리기를 누르세요.\n저장 완료 미확정 안내가 나오면, 취소로 종료한 뒤 다시 실행하여 리맵 문제 해결 → 실패한 Pico 저장 다시 시도를 사용하세요.' if self.temporary else '재시도: 남은 캡처 작업 정리\n취소: 미정리 상태로 종료 (캡처 프로세스가 남아 있을 수 있습니다.)'
            if messagebox.askretrycancel(title,str(error)+'\n'+note+'\n\n'+detail,parent=root):return False
        self.done=True;return True
