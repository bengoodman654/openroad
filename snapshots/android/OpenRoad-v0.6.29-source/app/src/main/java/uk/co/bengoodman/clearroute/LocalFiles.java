package uk.co.bengoodman.clearroute;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

public final class LocalFiles {
    private LocalFiles() {}

    public static String readUtf8(File file) throws Exception {
        try (FileInputStream input = new FileInputStream(file);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int read;
            while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
            return output.toString(StandardCharsets.UTF_8.name());
        }
    }

    public static void writeUtf8(File file, String text) throws Exception {
        try (FileOutputStream output = new FileOutputStream(file, false)) {
            output.write(text.getBytes(StandardCharsets.UTF_8));
            output.flush();
        }
    }
}
