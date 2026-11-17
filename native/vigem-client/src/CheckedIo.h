// Checked synchronous facade over overlapped I/O. No wait after immediate failure.
// Event/request storage stays alive until a pending operation completes.
template<class Issue, class Finish>
static BOOL ds5_checked_result(Issue issue, Finish finish)
{
    if (issue()) return TRUE;
    if (GetLastError() != ERROR_IO_PENDING) return FALSE;
    return finish();
}
static BOOL ds5_ioctl(HANDLE bus, DWORD code, void* input, DWORD inputSize,
    void* output, DWORD outputSize, DWORD* transferred, OVERLAPPED* ov)
{
    if (!ov->hEvent) { SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
    const HANDLE event = ov->hEvent;
    ZeroMemory(ov, sizeof(*ov)); ov->hEvent = event;
    if (!ResetEvent(event)) return FALSE;
    return ds5_checked_result(
        [&]() { return DeviceIoControl(bus, code, input, inputSize, output,
            outputSize, transferred, ov); },
        [&]() { return GetOverlappedResult(bus, ov, transferred, TRUE); });
}
#ifdef DS5LIGHT_TESTING
extern "C" __declspec(dllexport) DWORD ds5test_checked_io(DWORD initialError,
    DWORD completionError, DWORD* waited)
{
    *waited = 0;
    BOOL ok = ds5_checked_result(
        [&]() -> BOOL { SetLastError(initialError); return initialError == 0; },
        [&]() -> BOOL { ++*waited; SetLastError(completionError); return completionError == 0; });
    return ok ? ERROR_SUCCESS : GetLastError();
}
#endif
