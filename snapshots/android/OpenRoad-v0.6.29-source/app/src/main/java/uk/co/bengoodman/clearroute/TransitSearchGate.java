package uk.co.bengoodman.clearroute;

/** Thread-safe per-search delivery state. Always hold this object's monitor while dispatching callbacks. */
final class TransitSearchGate {
    private boolean closed;
    private boolean firstDelivered;

    synchronized boolean first() {
        if (closed || firstDelivered) return false;
        firstDelivered = true;
        return true;
    }
    synchronized boolean update() { return !closed && firstDelivered; }
    synchronized boolean progress() { return !closed && !firstDelivered; }
    synchronized boolean fail() {
        if (closed || firstDelivered) return false;
        closed = true;
        return true;
    }
    /** @return true if there was no first result and the caller should show a timeout. */
    synchronized boolean expire() {
        if (closed) return false;
        closed = true;
        return !firstDelivered;
    }
    synchronized void complete() { closed = true; }
}
