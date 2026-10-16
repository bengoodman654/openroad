package uk.co.bengoodman.clearroute;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.util.UUID;

/**
 * Device-specific signing identity for the owner's private OpenRoad transport server.
 * The EC private key is generated inside Android Keystore and is never exported.
 */
public final class DeviceAuth {
    private static final String PREFS = "openroad_transport_auth";
    private static final String PREF_DEVICE_ID = "device_id";
    private static final String PREF_PAIRED_URL = "paired_url";
    private static final String ALIAS = "openroad_transport_device_v1";
    private static final SecureRandom RNG = new SecureRandom();

    private DeviceAuth() {}

    public static String deviceId(Context context) {
        SharedPreferences p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String id = p.getString(PREF_DEVICE_ID, "");
        if (id != null && !id.isEmpty()) return id;
        id = UUID.randomUUID().toString();
        p.edit().putString(PREF_DEVICE_ID, id).apply();
        return id;
    }

    public static boolean hasKey() {
        try {
            KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
            ks.load(null);
            return ks.containsAlias(ALIAS);
        } catch (Exception ignored) { return false; }
    }

    public static KeyPair ensureKeyPair() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        if (ks.containsAlias(ALIAS)) {
            PublicKey pub = ks.getCertificate(ALIAS).getPublicKey();
            PrivateKey priv = (PrivateKey) ks.getKey(ALIAS, null);
            return new KeyPair(pub, priv);
        }
        KeyPairGenerator generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore");
        KeyGenParameterSpec spec = new KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY)
                .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setUserAuthenticationRequired(false)
                .build();
        generator.initialize(spec);
        return generator.generateKeyPair();
    }

    public static String publicKeyPem() throws Exception {
        byte[] der = ensureKeyPair().getPublic().getEncoded();
        String b64 = Base64.encodeToString(der, Base64.NO_WRAP);
        StringBuilder out = new StringBuilder("-----BEGIN PUBLIC KEY-----\n");
        for (int i = 0; i < b64.length(); i += 64) {
            out.append(b64, i, Math.min(i + 64, b64.length())).append('\n');
        }
        return out.append("-----END PUBLIC KEY-----\n").toString();
    }

    public static String nonce() {
        byte[] bytes = new byte[18];
        RNG.nextBytes(bytes);
        return Base64.encodeToString(bytes, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }

    public static String sign(String canonical) throws Exception {
        Signature signature = Signature.getInstance("SHA256withECDSA");
        signature.initSign(ensureKeyPair().getPrivate());
        signature.update(canonical.getBytes(StandardCharsets.UTF_8));
        return Base64.encodeToString(signature.sign(), Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }

    public static boolean isPaired(Context context, String baseUrl) {
        if (!hasKey()) return false;
        String expected = normaliseBaseUrl(baseUrl);
        String paired = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(PREF_PAIRED_URL, "");
        return !expected.isEmpty() && expected.equals(paired);
    }

    public static void markPaired(Context context, String baseUrl) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(PREF_PAIRED_URL, normaliseBaseUrl(baseUrl)).apply();
    }

    public static void clearPairing(Context context) {
        try {
            KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
            ks.load(null);
            if (ks.containsAlias(ALIAS)) ks.deleteEntry(ALIAS);
        } catch (Exception ignored) {}
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .remove(PREF_DEVICE_ID).remove(PREF_PAIRED_URL).apply();
    }

    public static String normaliseBaseUrl(String value) {
        String s = value == null ? "" : value.trim();
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        return s;
    }
}
