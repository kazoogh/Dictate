#include "dictate_native.h"

#include <windows.h>

namespace {

DictateHotkeyFn g_hotkey_cb = nullptr;
void* g_hotkey_user = nullptr;

}  // namespace

extern bool Hotkey_Init();
extern void Hotkey_Shutdown();
extern bool Hotkey_Register(unsigned int modifiers, unsigned int vk, int hotkey_id);
extern bool Hotkey_Unregister(int hotkey_id);

extern bool Paste_Text(const wchar_t* text, bool restore_clipboard);
extern bool Audio_Begin(const wchar_t* wav_path, int sample_rate);
extern bool Audio_End();

DICTATE_API int dictate_initialize(void) {
  return Hotkey_Init() ? 1 : 0;
}

DICTATE_API void dictate_shutdown(void) {
  Audio_End();
  Hotkey_Shutdown();
}

DICTATE_API int dictate_set_hotkey_callback(DictateHotkeyFn callback, void* user_data) {
  g_hotkey_cb = callback;
  g_hotkey_user = user_data;
  return 1;
}

void Dictate_OnHotkey(int hotkey_id) {
  if (g_hotkey_cb) {
    g_hotkey_cb(hotkey_id, g_hotkey_user);
  }
}

DICTATE_API int dictate_register_hotkey(unsigned int modifiers, unsigned int vk, int hotkey_id) {
  return Hotkey_Register(modifiers, vk, hotkey_id) ? 1 : 0;
}

DICTATE_API int dictate_unregister_hotkey(int hotkey_id) {
  return Hotkey_Unregister(hotkey_id) ? 1 : 0;
}

DICTATE_API int dictate_paste_text(const wchar_t* text, int restore_clipboard) {
  if (!text) {
    return 0;
  }
  return Paste_Text(text, restore_clipboard != 0) ? 1 : 0;
}

DICTATE_API int dictate_audio_begin(const wchar_t* wav_path, int sample_rate) {
  if (!wav_path) {
    return 0;
  }
  return Audio_Begin(wav_path, sample_rate) ? 1 : 0;
}

DICTATE_API int dictate_audio_end(void) {
  return Audio_End() ? 1 : 0;
}
