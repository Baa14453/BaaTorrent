import vapoursynth as vs
import os
import sys

core = vs.get_core(threads=15)

core.std.LoadPlugin("lib-linux/libsvpflow1_vs64.so")
core.std.LoadPlugin("lib-linux/libsvpflow2_vs64.so")
core.std.LoadPlugin("lib-linux/libffms2.so.4")

clip = core.ffms2.Source(source=file)
clip = clip.resize.Bicubic(format=vs.YUV420P8)

super_params="{scale:{up:0},gpu:1,pel:1,full:false}"
analyse_params="{block:{w:32,h:32},main:{search:{coarse:{type:2,distance:-5,bad:{range:0}},type:3,distance:-3},penalty:{pnbour:65},levels:4},refine:[{search:{distance:1}}]}"
smoothfps_params="{rate:{num:5,den:2},algo:23,mask:{cover:80},scene:{mode:0,limits:{scene:3000,blocks:40}}}"

super  = core.svp1.Super(clip,super_params)
vectors= core.svp1.Analyse(super["clip"],super["data"],clip,analyse_params)
smooth = core.svp2.SmoothFps(clip,super["clip"],super["data"],vectors["clip"],vectors["data"],smoothfps_params)
smooth = core.std.AssumeFPS(smooth,fpsnum=smooth.fps_num,fpsden=smooth.fps_den)

smooth.set_output()
