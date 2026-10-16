package uk.co.bengoodman.clearroute;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

/** Standalone deadline/delivery state contract test; runs without Android dependencies. */
public final class TransitSearchGateTest {
    private static void check(boolean result, String message) {
        if (!result) throw new AssertionError(message);
    }
    public static void main(String[] args) throws Exception {
        TransitSearchGate happy = new TransitSearchGate();
        check(happy.progress(), "progress accepted while pending");
        check(happy.first(), "first result accepted");
        check(!happy.first(), "duplicate first rejected");
        check(!happy.progress(), "progress after first rejected");
        check(happy.update(), "update after first accepted");
        check(!happy.expire(), "no error after successful result");
        check(!happy.update(), "late update rejected");
        check(!happy.fail(), "late failure rejected");
        TransitSearchGate expired = new TransitSearchGate();
        check(expired.expire(), "deadline triggers failure if no result");
        check(!expired.first(), "late first rejected");
        check(!expired.expire(), "no duplicate timeout");
        TransitSearchGate failed = new TransitSearchGate();
        check(failed.fail(), "failure accepted");
        check(!failed.fail() && !failed.first() && !failed.expire(), "failure terminal");
        TransitSearchGate completed = new TransitSearchGate();
        completed.complete();
        check(!completed.first() && !completed.progress(), "completion terminal");
        for (int i=0; i<200; i++) {
            TransitSearchGate raced = new TransitSearchGate();
            CountDownLatch ready = new CountDownLatch(2), start = new CountDownLatch(1);
            AtomicInteger delivered = new AtomicInteger();
            Thread first = new Thread(() -> {ready.countDown();await(start);if(raced.first()) delivered.incrementAndGet();});
            Thread deadline = new Thread(() -> {ready.countDown();await(start);if(raced.expire()) delivered.incrementAndGet();});
            first.start();deadline.start();ready.await();start.countDown();first.join();deadline.join();
            check(delivered.get()==1, "exactly one terminal first-or-timeout outcome");
        }
        System.out.println("TransitSearchGate: 207 assertions/groups passed (including 200 races)");
    }
    private static void await(CountDownLatch latch) {try{latch.await();}catch(InterruptedException e){Thread.currentThread().interrupt();}}
}
