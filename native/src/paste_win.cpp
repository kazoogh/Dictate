#include <windows.h>

#include <string>
#include <vector>

namespace {

void SendCtrlV() {
  INPUT inputs[4]{};
  inputs[0].type = INPUT_KEYBOARD;
  inputs[0].ki.wVk = VK_CONTROL;
  inputs[1].type = INPUT_KEYBOARD;
  inputs[1].ki.wVk = 'V';
  inputs[2].type = INPUT_KEYBOARD;
  inputs[2].ki.wVk = 'V';
  inputs[2].ki.dwFlags = KEYEVENTF_KEYUP;
  inputs[3].type = INPUT_KEYBOARD;
  inputs[3].ki.wVk = VK_CONTROL;
  inputs[3].ki.dwFlags = KEYEVENTF_KEYUP;
  SendInput(4, inputs, sizeof(INPUT));
}

std::wstring ReadClipboardText() {
  if (!OpenClipboard(nullptr)) {
    return L"";
  }
  HANDLE data = GetClipboardData(CF_UNICODETEXT);
  if (!data) {
    CloseClipboard();
    return L"";
  }
  const wchar_t* text = static_cast<const wchar_t*>(GlobalLock(data));
  std::wstring result = text ? text : L"";
  GlobalUnlock(data);
  CloseClipboard();
  return result;
}

bool WriteClipboardText(const std::wstring& text) {
  if (!OpenClipboard(nullptr)) {
    return false;
  }
  EmptyClipboard();
  const size_t bytes = (text.size() + 1) * sizeof(wchar_t);
  HGLOBAL mem = GlobalAlloc(GMEM_MOVEABLE, bytes);
  if (!mem) {
    CloseClipboard();
    return false;
  }
  void* locked = GlobalLock(mem);
  if (!locked) {
    GlobalFree(mem);
    CloseClipboard();
    return false;
  }
  memcpy(locked, text.c_str(), bytes);
  GlobalUnlock(mem);
  SetClipboardData(CF_UNICODETEXT, mem);
  CloseClipboard();
  return true;
}

}  // namespace

bool Paste_Text(const wchar_t* text, bool restore_clipboard) {
  const std::wstring original = restore_clipboard ? ReadClipboardText() : L"";
  if (!WriteClipboardText(text)) {
    return false;
  }
  Sleep(50);
  SendCtrlV();
  if (restore_clipboard) {
    Sleep(400);
    WriteClipboardText(original);
  }
  return true;
}
