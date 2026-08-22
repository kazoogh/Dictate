#pragma once

#ifdef _WIN32
  #ifdef DICTATE_NATIVE_EXPORTS
    #define DICTATE_API __declspec(dllexport)
  #else
    #define DICTATE_API __declspec(dllimport)
  #endif
#else
  #define DICTATE_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*DictateHotkeyFn)(int hotkey_id, void* user_data);

/* Win32 modifier flags: MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN */
DICTATE_API int dictate_initialize(void);
DICTATE_API void dictate_shutdown(void);
DICTATE_API int dictate_set_hotkey_callback(DictateHotkeyFn callback, void* user_data);
DICTATE_API int dictate_register_hotkey(unsigned int modifiers, unsigned int vk, int hotkey_id);
DICTATE_API int dictate_unregister_hotkey(int hotkey_id);
DICTATE_API int dictate_paste_text(const wchar_t* text, int restore_clipboard);
DICTATE_API int dictate_audio_begin(const wchar_t* wav_path, int sample_rate);
DICTATE_API int dictate_audio_end(void);

#ifdef __cplusplus
}
#endif
