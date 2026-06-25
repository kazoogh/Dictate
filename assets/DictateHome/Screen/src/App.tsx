import { useEffect } from "react";
import {
  AudioLines,
  Clock,
  Copy,
  Cpu,
  FileText,
  Gauge,
  HardDrive,
  Keyboard,
  Mic,
  Settings,
  ShieldCheck,
  Square,
  Trash2,
  Type,
  Wifi,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function App() {
  return (
    <div>
      <div className="bg-white text-zinc-950 w-full h-fit h-fit min-h-screen w-screen min-w-screen max-w-screen overflow-visible">
        <div className="flex mx-auto p-8 flex-col gap-6 w-285 h-239">
          <header className="flex justify-between items-center">
            <div className="flex items-center gap-4">
              <div className="size-12 rounded-xl bg-[#2b7fff] text-blue-50 flex justify-center items-center">
                <AudioLines className="size-6" />
              </div>
              <div className="flex flex-col gap-1">
                <h1 className="font-bold text-zinc-950 text-2xl leading-8 tracking-tight">
                  Dictate
                </h1>
                <p className="text-[#71717b] text-sm leading-5">
                  Local voice typing assistant
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="rounded-full bg-red-50 border-red-200 border-1 border-solid flex px-4 py-2 items-center gap-2">
                <Square className="size-3.5 fill-red-600 text-red-600" />
                <span className="font-medium text-red-600 text-sm leading-5">
                  Press End to Stop
                </span>
              </div>
              <Button
                className="size-10 rounded-xl"
                size="icon"
                variant="outline"
              >
                <Settings className="size-5" />
              </Button>
            </div>
          </header>
          <div className="min-h-0 flex flex-1 gap-6">
            <div className="min-h-0 flex flex-col flex-1 gap-4">
              <Card className="border-l-red-500 bg-[#FFF5F5] border-black/1 border-t-0 border-r-0 border-b-0 border-l-4 border-solid p-4 gap-3">
                <div className="flex items-center gap-4">
                  <div className="relative size-12 shrink-0 flex justify-center items-center">
                    <span className="inline-flex size-12 animate-ping rounded-full bg-red-400/40 absolute" />
                    <span className="relative inline-flex size-5 rounded-full bg-red-500" />
                  </div>
                  <div className="min-w-0 flex flex-col flex-1 gap-1">
                    <p className="font-bold text-zinc-950 text-base leading-6">
                      Recording…
                    </p>
                    <p className="text-[#71717b] text-sm leading-5">
                      Press your hotkey again to stop.
                    </p>
                  </div>
                  <div className="shrink-0 flex items-end gap-1 h-10">
                    <span className="animate-pulse rounded-full bg-red-300 w-1.5 h-4" />
                    <span className="animate-pulse rounded-full bg-red-400 w-1.5 h-8" />
                    <span className="animate-pulse rounded-full bg-red-300 w-1.5 h-5" />
                    <span className="animate-pulse rounded-full bg-red-400 w-1.5 h-10" />
                    <span className="animate-pulse rounded-full bg-red-300 w-1.5 h-6" />
                    <span className="animate-pulse rounded-full bg-red-400 w-1.5 h-9" />
                    <span className="animate-pulse rounded-full bg-red-300 w-1.5 h-3" />
                    <span className="animate-pulse rounded-full bg-red-400 w-1.5 h-7" />
                    <span className="animate-pulse rounded-full bg-red-300 w-1.5 h-5" />
                  </div>
                </div>
              </Card>
              <Card className="min-h-0 flex p-6 flex-col flex-1 gap-4">
                <CardHeader className="flex p-0 flex-row justify-between items-center gap-2">
                  <div className="flex items-center gap-2">
                    <FileText className="size-5 text-[#71717b]" />
                    <CardTitle className="font-semibold text-lg leading-7">
                      Transcriptions
                    </CardTitle>
                  </div>
                  <span className="font-medium rounded-full bg-zinc-100 text-zinc-900 text-xs leading-4 px-2.5 py-1">
                    3 items
                  </span>
                </CardHeader>
                <CardContent className="flex p-0 flex-col flex-1 gap-3 overflow-hidden">
                  <div className="rounded-xl bg-zinc-100/60 border-zinc-200 border-1 border-solid flex p-4 flex-col gap-2">
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-[#71717b] text-xs leading-4">
                        Today · 10:24 AM
                      </span>
                      <div className="flex items-center gap-1">
                        <Button
                          className="size-7 rounded-lg"
                          size="icon"
                          variant="ghost"
                        >
                          <Copy className="size-3.5 text-[#71717b]" />
                        </Button>
                        <Button
                          className="size-7 rounded-lg"
                          size="icon"
                          variant="ghost"
                        >
                          <Trash2 className="size-3.5 text-[#71717b]" />
                        </Button>
                      </div>
                    </div>
                    <p className="leading-relaxed text-zinc-950 text-sm leading-5">
                      Schedule the design review for Thursday afternoon and
                      share the latest mockups with the team beforehand.
                    </p>
                  </div>
                  <div className="rounded-xl bg-zinc-100/60 border-zinc-200 border-1 border-solid flex p-4 flex-col gap-2">
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-[#71717b] text-xs leading-4">
                        Today · 9:47 AM
                      </span>
                      <div className="flex items-center gap-1">
                        <Button
                          className="size-7 rounded-lg"
                          size="icon"
                          variant="ghost"
                        >
                          <Copy className="size-3.5 text-[#71717b]" />
                        </Button>
                        <Button
                          className="size-7 rounded-lg"
                          size="icon"
                          variant="ghost"
                        >
                          <Trash2 className="size-3.5 text-[#71717b]" />
                        </Button>
                      </div>
                    </div>
                    <p className="leading-relaxed text-zinc-950 text-sm leading-5">
                      Remember to follow up with the vendor about the updated
                      pricing and delivery timelines for next quarter.
                    </p>
                  </div>
                  <div className="rounded-xl bg-zinc-100/60 border-zinc-200 border-1 border-solid flex p-4 flex-col gap-2">
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-[#71717b] text-xs leading-4">
                        Yesterday · 4:12 PM
                      </span>
                      <div className="flex items-center gap-1">
                        <Button
                          className="size-7 rounded-lg"
                          size="icon"
                          variant="ghost"
                        >
                          <Copy className="size-3.5 text-[#71717b]" />
                        </Button>
                        <Button
                          className="size-7 rounded-lg"
                          size="icon"
                          variant="ghost"
                        >
                          <Trash2 className="size-3.5 text-[#71717b]" />
                        </Button>
                      </div>
                    </div>
                    <p className="leading-relaxed text-zinc-950 text-sm leading-5">
                      Draft the quarterly summary covering key wins, blockers,
                      and the roadmap priorities for the leadership sync.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
            <div className="shrink-0 flex flex-col gap-4 w-80">
              <div className="grid grid-cols-2 gap-4">
                <Card className="p-4 gap-2">
                  <CardHeader className="flex p-0 flex-row items-center gap-2">
                    <Clock className="size-4 text-[#2b7fff]" />
                    <span className="font-medium text-[#71717b] text-xs leading-4">
                      Total Time
                    </span>
                  </CardHeader>
                  <CardContent className="p-0 gap-1">
                    <p className="font-bold text-zinc-950 text-2xl leading-8">
                      4h 12m
                    </p>
                  </CardContent>
                </Card>
                <Card className="p-4 gap-2">
                  <CardHeader className="flex p-0 flex-row items-center gap-2">
                    <Type className="size-4 text-[#2b7fff]" />
                    <span className="font-medium text-[#71717b] text-xs leading-4">
                      Words
                    </span>
                  </CardHeader>
                  <CardContent className="p-0 gap-1">
                    <p className="font-bold text-zinc-950 text-2xl leading-8">
                      12,480
                    </p>
                  </CardContent>
                </Card>
                <Card className="p-4 gap-2">
                  <CardHeader className="flex p-0 flex-row items-center gap-2">
                    <Mic className="size-4 text-[#2b7fff]" />
                    <span className="font-medium text-[#71717b] text-xs leading-4">
                      Sessions
                    </span>
                  </CardHeader>
                  <CardContent className="p-0 gap-1">
                    <p className="font-bold text-zinc-950 text-2xl leading-8">
                      87
                    </p>
                  </CardContent>
                </Card>
                <Card className="p-4 gap-2">
                  <CardHeader className="flex p-0 flex-row items-center gap-2">
                    <Gauge className="size-4 text-[#2b7fff]" />
                    <span className="font-medium text-[#71717b] text-xs leading-4">
                      Avg WPM
                    </span>
                  </CardHeader>
                  <CardContent className="p-0 gap-1">
                    <p className="font-bold text-zinc-950 text-2xl leading-8">
                      142
                    </p>
                  </CardContent>
                </Card>
              </div>
              <Card className="p-6 gap-4">
                <CardHeader className="flex p-0 flex-row items-center gap-3">
                  <div className="size-10 rounded-xl bg-[#2b7fff]/10 flex justify-center items-center">
                    <ShieldCheck className="size-5 text-[#2b7fff]" />
                  </div>
                  <div className="flex flex-col gap-0.5">
                    <CardTitle className="font-semibold text-base leading-6">
                      Local Mode
                    </CardTitle>
                    <span className="text-[#71717b] text-xs leading-4">
                      On-device processing
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="flex p-0 flex-col gap-3">
                  <p className="leading-relaxed text-[#71717b] text-sm leading-5">
                    All transcription happens on your machine. No audio ever
                    leaves your device.
                  </p>
                  <div className="rounded-lg bg-[#2b7fff]/10 flex px-3 py-2 items-center gap-2">
                    <Wifi className="size-4 text-[#2b7fff]" />
                    <span className="font-medium text-[#2b7fff] text-xs leading-4">
                      No internet required
                    </span>
                  </div>
                </CardContent>
              </Card>
              <Card className="flex p-6 flex-col justify-center items-center flex-1 gap-4">
                <div className="relative size-20 flex justify-center items-center">
                  <span className="inline-flex size-20 animate-ping rounded-full bg-red-400/30 absolute" />
                  <div className="relative size-16 rounded-full bg-red-500 text-white flex justify-center items-center">
                    <Mic className="size-7" />
                  </div>
                </div>
                <div className="flex flex-col items-center gap-1">
                  <p className="font-semibold text-zinc-950 text-sm leading-5">
                    Listening
                  </p>
                  <p className="text-center text-[#71717b] text-xs leading-4">
                    Speak naturally — text appears where your cursor is.
                  </p>
                </div>
              </Card>
            </div>
          </div>
          <div className="rounded-xl bg-zinc-100/60 border-zinc-200 border-1 border-solid flex px-4 py-3 justify-between items-center">
            <div className="flex items-center gap-2">
              <span className="relative size-2.5 flex">
                <span className="inline-flex size-2.5 animate-ping rounded-full bg-red-400 absolute" />
                <span className="relative inline-flex size-2.5 rounded-full bg-red-500" />
              </span>
              <span className="font-bold text-red-600 text-sm leading-5">
                Recording…
              </span>
            </div>
            <div className="text-[#71717b] text-xs leading-4 flex items-center gap-4">
              <span className="flex items-center gap-1.5">
                <Cpu className="size-3.5" />
                Model: base.en
              </span>
              <span className="flex items-center gap-1.5">
                <HardDrive className="size-3.5" />
                Offline
              </span>
              <span className="flex items-center gap-1.5">
                <Keyboard className="size-3.5" />
                Hotkey: End
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
