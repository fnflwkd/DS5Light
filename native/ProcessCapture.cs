// Independent WASAPI process-loopback adapter. No recording or device writes.
using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using System.Collections.Concurrent;

[StructLayout(LayoutKind.Sequential)] struct Activation { public int Type; public uint Pid; public int Mode; }
[StructLayout(LayoutKind.Explicit, Size=24)] struct Variant {
    [FieldOffset(0)] public ushort Type;
    [FieldOffset(8)] public uint Size;
    [FieldOffset(16)] public IntPtr Data;
}
[StructLayout(LayoutKind.Sequential, Pack=2)] struct Wave {
    public ushort Tag, Channels; public uint Rate, BytesPerSecond;
    public ushort Align, Bits, Extra, ValidBits; public uint Mask; public Guid SubFormat;
}
[ComImport, Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface AudioClient {
    [PreserveSig] int Initialize(int mode,uint flags,long duration,long period,ref Wave format,IntPtr session);
    [PreserveSig] int GetBufferSize(out uint size);
    [PreserveSig] int GetStreamLatency(out long value);
    [PreserveSig] int GetCurrentPadding(out uint value);
    [PreserveSig] int IsFormatSupported(int mode,IntPtr format,out IntPtr closest);
    [PreserveSig] int GetMixFormat(out IntPtr format);
    [PreserveSig] int GetDevicePeriod(out long normal,out long minimum);
    [PreserveSig] int Start(); [PreserveSig] int Stop(); [PreserveSig] int Reset();
    [PreserveSig] int SetEventHandle(IntPtr value);
    [PreserveSig] int GetService(ref Guid iid,[MarshalAs(UnmanagedType.IUnknown)] out object service);
}
[ComImport, Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface CaptureClient {
    [PreserveSig] int GetBuffer(out IntPtr data,out uint frames,out uint flags,out ulong device,out ulong qpc);
    [PreserveSig] int ReleaseBuffer(uint frames);
    [PreserveSig] int GetNextPacketSize(out uint frames);
}
[ComImport, Guid("72A22D78-CDE4-431d-B8CC-843A71199B6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface AsyncOperation {
    [PreserveSig] int GetActivateResult(out int result,[MarshalAs(UnmanagedType.IUnknown)] out object audio);
}
[ComVisible(true), Guid("41D949AB-9862-444a-80F6-C261334DA5EB"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface Completion { [PreserveSig] int ActivateCompleted(AsyncOperation operation); }
[ComVisible(true), Guid("94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface Agile { }
[ComVisible(true), ClassInterface(ClassInterfaceType.None)]
public class Completed : Completion, Agile {
    public readonly ManualResetEvent Done=new ManualResetEvent(false);
    public object Audio; public int Result;
    public int ActivateCompleted(AsyncOperation op) {
        try { int result; object audio; int hr=op.GetActivateResult(out result,out audio); Result=hr<0?hr:result; Audio=audio; }
        catch(Exception e) { Result=Marshal.GetHRForException(e); }
        finally { Done.Set(); }
        return 0;
    }
}
class Packet { public byte[] Data; public double Time; public Packet(byte[] d,double t) {Data=d;Time=t;} }
class Program {
    [DllImport("Mmdevapi.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
    static extern int ActivateAudioInterfaceAsync(string device,ref Guid iid,ref Variant activation,
        [MarshalAs(UnmanagedType.Interface)] Completion callback,out AsyncOperation operation);
    static volatile bool running=true; static string stage="activate call";
    static void Check(int hr) { if(hr<0) Marshal.ThrowExceptionForHR(hr); }
    [MTAThread] static int Main(string[] args) {
        AudioClient audio=null; CaptureClient capture=null; IntPtr config=IntPtr.Zero;
        try {
            if(args.Length<2) throw new ArgumentException("Usage: ProcessCapture PID channels [seconds]");
            uint pid=uint.Parse(args[0]); ushort channels=ushort.Parse(args[1]);
            if(channels!=2 && channels!=6) throw new ArgumentException("channels must be 2 or 6");
            double seconds=args.Length>2?double.Parse(args[2],System.Globalization.CultureInfo.InvariantCulture):0;
            Process target=Process.GetProcessById((int)pid);
            var cb=new Completed(); var ap=new Activation { Type=1, Pid=pid, Mode=0 };
            config=Marshal.AllocCoTaskMem(Marshal.SizeOf(ap)); Marshal.StructureToPtr(ap,config,false);
            var variant=new Variant { Type=65, Size=(uint)Marshal.SizeOf(ap), Data=config };
            Guid audioIID=typeof(AudioClient).GUID; AsyncOperation operation;
            Check(ActivateAudioInterfaceAsync("VAD\\Process_Loopback",ref audioIID,ref variant,cb,out operation));
            if(!cb.Done.WaitOne(5000)) throw new TimeoutException("Activation timed out");
            stage="activation result"; Check(cb.Result); audio=(AudioClient)cb.Audio;
            Wave format=new Wave {Tag=65534,Channels=channels,Rate=48000,BytesPerSecond=(uint)(48000*channels*2),
                Align=(ushort)(channels*2),Bits=16,Extra=22,ValidBits=16,Mask=channels==6?63u:3u,
                SubFormat=new Guid("00000001-0000-0010-8000-00aa00389b71")};
            stage="initialize"; Check(audio.Initialize(0,0x80060000,0,0,ref format,IntPtr.Zero));
            Guid captureIID=typeof(CaptureClient).GUID; object obj; Check(audio.GetService(ref captureIID,out obj));
            capture=(CaptureClient)obj;
            var ready=new AutoResetEvent(false); Check(audio.SetEventHandle(ready.SafeWaitHandle.DangerousGetHandle()));
            var queue=new BlockingCollection<Packet>(8); long drops=0, discontinuities=0, framesTotal=0;
            var output=new BinaryWriter(Console.OpenStandardOutput());
            output.Write(new byte[]{68,83,53,80}); output.Write((int)channels); output.Write(48000); output.Flush();
            Thread writer=new Thread(delegate() {
                try { foreach(var p in queue.GetConsumingEnumerable()) { output.Write(p.Data.Length); output.Write(p.Time); output.Write(p.Data); output.Flush(); } }
                catch { running=false; }
            }); writer.IsBackground=true; writer.Start();
            Thread control=new Thread(delegate() { try { Console.ReadLine(); } catch {} running=false; });
            control.IsBackground=true; control.Start();
            Check(audio.Start()); Console.Error.WriteLine("READY pid="+pid+" channels="+channels+" rate=48000");
            var elapsed=Stopwatch.StartNew();
            while(running && (seconds<=0 || elapsed.Elapsed.TotalSeconds<seconds)) {
                if(target.HasExited) { Console.Error.WriteLine("TARGET_EXITED"); break; }
                ready.WaitOne(100);
                uint pending; Check(capture.GetNextPacketSize(out pending));
                while(pending>0 && running) {
                    IntPtr data; uint n,flags; ulong position,qpc;
                    Check(capture.GetBuffer(out data,out n,out flags,out position,out qpc));
                    try {
                        if((flags&1)!=0) discontinuities++;
                        byte[] bytes=new byte[checked((int)n*format.Align)];
                        if((flags&2)==0) Marshal.Copy(data,bytes,0,bytes.Length);
                        double stamp=(double)Stopwatch.GetTimestamp()/Stopwatch.Frequency;
                        Packet packet=new Packet(bytes,stamp);
                        if(!queue.TryAdd(packet)) { Packet removed; queue.TryTake(out removed); queue.TryAdd(packet); drops++; }
                        framesTotal+=n;
                    } finally { Check(capture.ReleaseBuffer(n)); }
                    Check(capture.GetNextPacketSize(out pending));
                }
            }
            Check(audio.Stop()); queue.CompleteAdding(); writer.Join(500);
            Console.Error.WriteLine("STOP frames="+framesTotal+" drops="+drops+" discontinuities="+discontinuities);
            GC.KeepAlive(cb); GC.KeepAlive(operation); GC.KeepAlive(ready);
            return 0;
        } catch(Exception e) { Console.Error.WriteLine("ERROR "+stage+" 0x"+Marshal.GetHRForException(e).ToString("X8")+" "+e.Message); return 1; }
        finally { running=false; if(audio!=null) { try{audio.Stop();}catch{} } if(config!=IntPtr.Zero) Marshal.FreeCoTaskMem(config); }
    }
}

