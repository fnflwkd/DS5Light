// Test DLL only. Uses real Windows threads/events, never opens a driver.
static volatile LONG test_mode = 0, test_issues = 0, test_cancels = 0, test_drained = 0;
extern "C" __declspec(dllexport) void ds5test_connected(PVIGEM_TARGET target)
{ target->State = VIGEM_TARGET_CONNECTED; }
extern "C" __declspec(dllexport) void ds5test_prepare(PVIGEM_CLIENT client, PVIGEM_TARGET target, LONG mode)
{
    client->hBusDevice = CreateEvent(nullptr, TRUE, FALSE, nullptr);
    target->SerialNo = 1;
    test_mode = mode; test_issues = test_cancels = test_drained = 0;
}
extern "C" __declspec(dllexport) LONG ds5test_stat(LONG index)
{
    if (index == 0) return InterlockedCompareExchange(&test_issues, 0, 0);
    if (index == 1) return InterlockedCompareExchange(&test_cancels, 0, 0);
    return InterlockedCompareExchange(&test_drained, 0, 0);
}
static BOOL ds5_issue(HANDLE, XUSB_REQUEST_NOTIFICATION* request, OVERLAPPED* ov)
{
    LONG n = InterlockedIncrement(&test_issues);
    if (test_mode == 2) { SetLastError(ERROR_DEVICE_NOT_CONNECTED); return FALSE; }
    if ((test_mode == 1 || test_mode == 3 || test_mode == 4) && n == 1) {
        request->LargeMotor = 123; request->SmallMotor = 45;
        if (test_mode == 1) return TRUE;
        SetEvent(ov->hEvent); // overlapped completion, not synchronous success
    }
    SetLastError(ERROR_IO_PENDING); return FALSE;
}
static void ds5_cancel(HANDLE, OVERLAPPED*) { InterlockedIncrement(&test_cancels); }
static BOOL ds5_finish(HANDLE, OVERLAPPED*, BOOL wait)
{
    if (!wait) {
        if (test_mode == 4) { SetLastError(ERROR_IO_INCOMPLETE); return FALSE; }
        return TRUE;
    }
    Sleep(20); // model delayed cancellation completion before buffers can be freed
    InterlockedIncrement(&test_drained);
    SetLastError(ERROR_OPERATION_ABORTED); return FALSE;
}
