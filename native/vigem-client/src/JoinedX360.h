// DS5Light additions, MIT. Included once in ViGEmClient.cpp.
// No detached thread, no polling, no callback pointer mutation before join.
#ifdef DS5LIGHT_TESTING
#include "TestNotificationIo.h"
#else
static BOOL ds5_issue(HANDLE bus, XUSB_REQUEST_NOTIFICATION* request, OVERLAPPED* ov)
{
    DWORD count = 0;
    return DeviceIoControl(bus, IOCTL_XUSB_REQUEST_NOTIFICATION, request, request->Size,
        request, request->Size, &count, ov);
}
static BOOL ds5_finish(HANDLE bus, OVERLAPPED* ov, BOOL wait)
{
    DWORD count = 0;
    return GetOverlappedResult(bus, ov, &count, wait);
}
static void ds5_cancel(HANDLE bus, OVERLAPPED* ov) { CancelIoEx(bus, ov); }
#endif

static DWORD WINAPI ds5_x360_receive(LPVOID parameter)
{
    const auto target = static_cast<PVIGEM_TARGET>(parameter);
    // Publish the thread handle/id before any callback can try to stop itself.
    WaitForSingleObject(target->NotificationStartedEvent, INFINITE);
    const auto client = target->NotificationClient;
    const auto notify = reinterpret_cast<PFN_VIGEM_X360_NOTIFICATION>(target->Notification);
    const auto user = target->NotificationUserData;
    OVERLAPPED ov = {};
    ov.hEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);
    if (!ov.hEvent) {
        InterlockedExchange(&target->NotificationError, GetLastError());
        return 0;
    }
    HANDLE events[] = {target->CancelNotificationThreadEvent, ov.hEvent};
    while (WaitForSingleObject(events[0], 0) == WAIT_TIMEOUT) {
        XUSB_REQUEST_NOTIFICATION request;
        XUSB_REQUEST_NOTIFICATION_INIT(&request, target->SerialNo);
        ResetEvent(ov.hEvent);
        BOOL completed = ds5_issue(client->hBusDevice, &request, &ov);
        if (!completed && GetLastError() != ERROR_IO_PENDING) {
            InterlockedExchange(&target->NotificationError, GetLastError());
            break; // terminal failure, never spin on a disconnected driver
        }
        if (!completed) {
            const DWORD result = WaitForMultipleObjects(2, events, FALSE, INFINITE);
            if (result != WAIT_OBJECT_0 + 1) {
                if (result == WAIT_FAILED)
                    InterlockedExchange(&target->NotificationError, GetLastError());
                ds5_cancel(client->hBusDevice, &ov);
                ds5_finish(client->hBusDevice, &ov, TRUE);
                // The OVERLAPPED and request buffers must outlive cancellation.
                break;
            }
            completed = ds5_finish(client->hBusDevice, &ov, FALSE);
            if (!completed) {
                InterlockedExchange(&target->NotificationError, GetLastError());
                ds5_cancel(client->hBusDevice, &ov);
                ds5_finish(client->hBusDevice, &ov, TRUE);
                break;
            }
        }
        if (WaitForSingleObject(events[0], 0) != WAIT_TIMEOUT) break;
        notify(client, target, request.LargeMotor, request.SmallMotor, request.LedNumber, user);
    }
    CloseHandle(ov.hEvent);
    return 0;
}

extern "C" __declspec(dllexport) DWORD ds5light_client_abi() { return 2; }
extern "C" __declspec(dllexport) DWORD ds5light_x360_error(PVIGEM_TARGET target)
{
    return target ? InterlockedCompareExchange(&target->NotificationError, 0, 0) : ERROR_INVALID_HANDLE;
}
extern "C" __declspec(dllexport) BOOL ds5light_x360_stop(PVIGEM_TARGET target)
{
    if (!target) return TRUE;
    if (target->NotificationThread) {
        if (GetCurrentThreadId() == target->NotificationThreadId) {
            SetLastError(ERROR_POSSIBLE_DEADLOCK);
            return FALSE;
        }
        if (!SetEvent(target->CancelNotificationThreadEvent)) return FALSE;
        if (WaitForSingleObject(target->NotificationThread, INFINITE) != WAIT_OBJECT_0) return FALSE;
        CloseHandle(target->NotificationThread);
        target->NotificationThread = nullptr;
        target->NotificationThreadId = 0;
    }
    if (target->CancelNotificationThreadEvent) {
        CloseHandle(target->CancelNotificationThreadEvent);
        target->CancelNotificationThreadEvent = nullptr;
    }
    if (target->NotificationStartedEvent) {
        CloseHandle(target->NotificationStartedEvent);
        target->NotificationStartedEvent = nullptr;
    }
    target->Notification = nullptr;
    target->NotificationUserData = nullptr;
    target->NotificationClient = nullptr;
    return TRUE;
}

VIGEM_ERROR vigem_target_x360_register_notification(PVIGEM_CLIENT client,
    PVIGEM_TARGET target, PFN_VIGEM_X360_NOTIFICATION notify, LPVOID user)
{
    if (!client || client->hBusDevice == INVALID_HANDLE_VALUE) return VIGEM_ERROR_BUS_INVALID_HANDLE;
    if (!target || !target->SerialNo || !notify) return VIGEM_ERROR_INVALID_TARGET;
    if (target->NotificationThread) return VIGEM_ERROR_CALLBACK_ALREADY_REGISTERED;
    target->CancelNotificationThreadEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);
    if (!target->CancelNotificationThreadEvent) return VIGEM_ERROR_WINAPI;
    target->NotificationStartedEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);
    if (!target->NotificationStartedEvent) {
        ds5light_x360_stop(target);
        return VIGEM_ERROR_WINAPI;
    }
    target->Notification = reinterpret_cast<FARPROC>(notify);
    target->NotificationUserData = user;
    target->NotificationClient = client;
    InterlockedExchange(&target->NotificationError, 0);
    target->NotificationThread = CreateThread(nullptr, 0, ds5_x360_receive, target, 0,
        &target->NotificationThreadId);
    if (!target->NotificationThread) {
        ds5light_x360_stop(target);
        return VIGEM_ERROR_WINAPI;
    }
    SetEvent(target->NotificationStartedEvent);
    return VIGEM_ERROR_NONE;
}
