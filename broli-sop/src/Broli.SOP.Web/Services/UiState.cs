namespace Broli.SOP.Web.Services;

/// <summary>Per-tab UI state shared by the layout and pages (busy indicator, meeting mode).</summary>
public sealed class UiState
{
    private int _busy;
    public bool Busy => _busy > 0;
    public bool MeetingMode { get; private set; }
    public event Action? Changed;

    public IDisposable BeginBusy()
    {
        Interlocked.Increment(ref _busy);
        Changed?.Invoke();
        return new Releaser(this);
    }

    public void ToggleMeeting()
    {
        MeetingMode = !MeetingMode;
        Changed?.Invoke();
    }

    private sealed class Releaser(UiState s) : IDisposable
    {
        private int _done;
        public void Dispose()
        {
            if (Interlocked.Exchange(ref _done, 1) == 1) return;
            Interlocked.Decrement(ref s._busy);
            s.Changed?.Invoke();
        }
    }
}
