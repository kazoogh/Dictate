#include <windows.h>

#include <atomic>
#include <thread>

void Dictate_OnHotkey(int hotkey_id);

namespace {

constexpr UINT WM_DICTATE_HOTKEY = WM_APP + 42;
constexpr int HOTKEY_BASE_ID = 0xD1C7;

HWND g_hwnd = nullptr;
std::thread g_thread;
std::atomic<bool> g_running{false};

LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam) {
  if (msg == WM_HOTKEY) {
    const int hotkey_id = static_cast<int>(wparam) - HOTKEY_BASE_ID;
    Dictate_OnHotkey(hotkey_id);
    return 0;
  }
  if (msg == WM_DESTROY) {
    PostQuitMessage(0);
    return 0;
  }
  return DefWindowProcW(hwnd, msg, wparam, lparam);
}

void MessageLoop() {
  HINSTANCE instance = GetModuleHandleW(nullptr);
  const wchar_t* cls = L"DictateNativeHotkeyWindow";
  WNDCLASSW wc{};
  wc.lpfnWndProc = WndProc;
  wc.hInstance = instance;
  wc.lpszClassName = cls;
  RegisterClassW(&wc);

  g_hwnd = CreateWindowExW(
      0, cls, L"DictateNativeHotkey", 0, 0, 0, 0, 0, HWND_MESSAGE, nullptr, instance, nullptr);
  if (!g_hwnd) {
    g_running = false;
    return;
  }

  MSG msg{};
  while (g_running && GetMessageW(&msg, nullptr, 0, 0) > 0) {
    TranslateMessage(&msg);
    DispatchMessageW(&msg);
  }

  if (g_hwnd) {
    DestroyWindow(g_hwnd);
    g_hwnd = nullptr;
  }
}

}  // namespace

bool Hotkey_Init() {
  if (g_running) {
    return true;
  }
  g_running = true;
  g_thread = std::thread(MessageLoop);
  for (int i = 0; i < 50 && !g_hwnd; ++i) {
    Sleep(10);
  }
  return g_hwnd != nullptr;
}

void Hotkey_Shutdown() {
  if (!g_running) {
    return;
  }
  g_running = false;
  if (g_hwnd) {
    PostMessageW(g_hwnd, WM_CLOSE, 0, 0);
  }
  if (g_thread.joinable()) {
    g_thread.join();
  }
}

bool Hotkey_Register(unsigned int modifiers, unsigned int vk, int hotkey_id) {
  if (!g_hwnd) {
    return false;
  }
  const int id = HOTKEY_BASE_ID + hotkey_id;
  UnregisterHotKey(g_hwnd, id);
  return RegisterHotKey(g_hwnd, id, modifiers, vk) != 0;
}

bool Hotkey_Unregister(int hotkey_id) {
  if (!g_hwnd) {
    return false;
  }
  return UnregisterHotKey(g_hwnd, HOTKEY_BASE_ID + hotkey_id) != 0;
}
