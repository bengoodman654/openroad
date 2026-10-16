package uk.co.bengoodman.clearroute;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Small Android-Keystore-backed credential store. Values are encrypted before they are
 * persisted in SharedPreferences. The TomTom compatibility helpers are kept so older code
 * and existing installs continue to work unchanged.
 */
public final class SecureStore {
    private static final String PREFS = "clearroute_secure";
    private static final String ALIAS = "clearroute_key";
    private static final String TOMTOM = "tomtom_api_key";

    private SecureStore() {}

    private static SecretKey key() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        if (ks.containsAlias(ALIAS)) return (SecretKey) ks.getKey(ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build());
        return generator.generateKey();
    }

    private static String valueName(String name) { return "secret_" + name; }
    private static String ivName(String name) { return "secret_" + name + "_iv"; }

    public static void saveSecret(Context context, String name, String value) throws Exception {
        String cleanName = name == null ? "" : name.trim();
        if (cleanName.isEmpty()) throw new IllegalArgumentException("Credential name is empty");
        String cleanValue = value == null ? "" : value.trim();
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (cleanValue.isEmpty()) {
            prefs.edit().remove(valueName(cleanName)).remove(ivName(cleanName)).apply();
            return;
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] encrypted = cipher.doFinal(cleanValue.getBytes(StandardCharsets.UTF_8));
        prefs.edit()
                .putString(valueName(cleanName), Base64.encodeToString(encrypted, Base64.NO_WRAP))
                .putString(ivName(cleanName), Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP))
                .apply();
    }

    public static String getSecret(Context context, String name) {
        try {
            String cleanName = name == null ? "" : name.trim();
            if (cleanName.isEmpty()) return "";
            SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String value = prefs.getString(valueName(cleanName), null);
            String iv = prefs.getString(ivName(cleanName), null);
            if (value == null || iv == null) return "";
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)));
            byte[] decoded = cipher.doFinal(Base64.decode(value, Base64.NO_WRAP));
            return new String(decoded, StandardCharsets.UTF_8);
        } catch (Exception ignored) {
            return "";
        }
    }

    public static void clearSecret(Context context, String name) {
        if (name == null || name.trim().isEmpty()) return;
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .remove(valueName(name.trim())).remove(ivName(name.trim())).apply();
    }

    public static void saveApiKey(Context context, String apiKey) throws Exception {
        saveSecret(context, TOMTOM, apiKey);
    }

    public static String getApiKey(Context context) {
        return getSecret(context, TOMTOM);
    }

    public static void clearApiKey(Context context) {
        clearSecret(context, TOMTOM);
    }
}
