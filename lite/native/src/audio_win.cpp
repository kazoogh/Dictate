#include <windows.h>
#include <mmsystem.h>

#include <atomic>
#include <cstdint>
#include <fstream>
#include <mutex>
#include <string>
#include <vector>

#pragma comment(lib, "winmm.lib")

namespace {

HWAVEIN g_wave_in = nullptr;
std::wstring g_wav_path;
std::vector<int16_t> g_samples;
std::mutex g_mutex;
std::atomic<bool> g_recording{false};
int g_sample_rate = 16000;

void CALLBACK WaveInCallback(HWAVEIN hwi, UINT msg, DWORD_PTR instance, DWORD_PTR param1, DWORD_PTR param2) {
  if (msg != WIM_DATA || !g_recording.load()) {
    return;
  }
  auto* header = reinterpret_cast<WAVEHDR*>(param1);
  if (!header || !(header->dwFlags & WHDR_DONE)) {
    return;
  }
  const auto* data = reinterpret_cast<const int16_t*>(header->lpData);
  const size_t count = header->dwBytesRecorded / sizeof(int16_t);
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_samples.insert(g_samples.end(), data, data + count);
  }
  waveInAddBuffer(hwi, header, sizeof(WAVEHDR));
}

bool WriteWav(const std::wstring& path, const std::vector<int16_t>& samples, int sample_rate) {
  std::ofstream out(path, std::ios::binary);
  if (!out) {
    return false;
  }
  const uint32_t data_size = static_cast<uint32_t>(samples.size() * sizeof(int16_t));
  const uint32_t riff_size = 36 + data_size;
  const uint16_t channels = 1;
  const uint16_t bits = 16;
  const uint32_t byte_rate = sample_rate * channels * bits / 8;
  const uint16_t block_align = channels * bits / 8;

  out.write("RIFF", 4);
  out.write(reinterpret_cast<const char*>(&riff_size), 4);
  out.write("WAVE", 4);
  out.write("fmt ", 4);
  uint32_t fmt_size = 16;
  uint16_t audio_format = 1;
  out.write(reinterpret_cast<const char*>(&fmt_size), 4);
  out.write(reinterpret_cast<const char*>(&audio_format), 2);
  out.write(reinterpret_cast<const char*>(&channels), 2);
  out.write(reinterpret_cast<const char*>(&sample_rate), 4);
  out.write(reinterpret_cast<const char*>(&byte_rate), 4);
  out.write(reinterpret_cast<const char*>(&block_align), 2);
  out.write(reinterpret_cast<const char*>(&bits), 2);
  out.write("data", 4);
  out.write(reinterpret_cast<const char*>(&data_size), 4);
  if (!samples.empty()) {
    out.write(reinterpret_cast<const char*>(samples.data()), data_size);
  }
  return static_cast<bool>(out);
}

}  // namespace

bool Audio_End();

bool Audio_Begin(const wchar_t* wav_path, int sample_rate) {
  Audio_End();
  g_wav_path = wav_path;
  g_sample_rate = sample_rate > 0 ? sample_rate : 16000;
  g_samples.clear();

  WAVEFORMATEX format{};
  format.wFormatTag = WAVE_FORMAT_PCM;
  format.nChannels = 1;
  format.nSamplesPerSec = static_cast<DWORD>(g_sample_rate);
  format.wBitsPerSample = 16;
  format.nBlockAlign = format.nChannels * format.wBitsPerSample / 8;
  format.nAvgBytesPerSec = format.nSamplesPerSec * format.nBlockAlign;

  MMRESULT result = waveInOpen(&g_wave_in, WAVE_MAPPER, &format, reinterpret_cast<DWORD_PTR>(WaveInCallback), 0,
                               CALLBACK_FUNCTION);
  if (result != MMSYSERR_NOERROR) {
    g_wave_in = nullptr;
    return false;
  }

  constexpr int kBufferCount = 4;
  constexpr int kBufferBytes = 4096;
  static WAVEHDR headers[kBufferCount];
  static std::vector<char> buffers[kBufferCount];

  for (int i = 0; i < kBufferCount; ++i) {
    buffers[i].assign(kBufferBytes, 0);
    headers[i] = {};
    headers[i].lpData = buffers[i].data();
    headers[i].dwBufferLength = kBufferBytes;
    waveInPrepareHeader(g_wave_in, &headers[i], sizeof(WAVEHDR));
    waveInAddBuffer(g_wave_in, &headers[i], sizeof(WAVEHDR));
  }

  g_recording = true;
  return waveInStart(g_wave_in) == MMSYSERR_NOERROR;
}

bool Audio_End() {
  if (!g_wave_in) {
    return true;
  }
  g_recording = false;
  waveInStop(g_wave_in);
  waveInReset(g_wave_in);
  waveInClose(g_wave_in);
  g_wave_in = nullptr;

  std::vector<int16_t> samples;
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    samples.swap(g_samples);
  }
  if (g_wav_path.empty()) {
    return false;
  }
  return WriteWav(g_wav_path, samples, g_sample_rate);
}
