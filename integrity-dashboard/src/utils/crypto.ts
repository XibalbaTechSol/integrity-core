/**
 * Xibalba Sovereign Cryptography — Real Storage Utility
 * Uses Web Crypto API (AES-GCM) for local encryption.
 */

export const encryptData = async (data: string, password: string): Promise<{ ciphertext: string; iv: string }> => {
    const encoder = new TextEncoder();
    const encodedData = encoder.encode(data);

    // Derive a key from the password
    const passwordKey = await window.crypto.subtle.importKey(
        "raw",
        encoder.encode(password),
        { name: "PBKDF2" },
        false,
        ["deriveKey"]
    );

    const salt = window.crypto.getRandomValues(new Uint8Array(16));
    const encryptionKey = await window.crypto.subtle.deriveKey(
        {
            name: "PBKDF2",
            salt: salt,
            iterations: 100000,
            hash: "SHA-256",
        },
        passwordKey,
        { name: "AES-GCM", length: 256 },
        false,
        ["encrypt"]
    );

    const iv = window.crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await window.crypto.subtle.encrypt(
        { name: "AES-GCM", iv: iv },
        encryptionKey,
        encodedData
    );

    return {
        ciphertext: btoa(String.fromCharCode(...new Uint8Array(ciphertext))),
        iv: btoa(String.fromCharCode(...iv)) + ":" + btoa(String.fromCharCode(...salt)),
    };
};

export const decryptData = async (ciphertext: string, ivWithSalt: string, password: string): Promise<string> => {
    const [ivB64, saltB64] = ivWithSalt.split(":");
    const encoder = new TextEncoder();
    const iv = new Uint8Array(atob(ivB64).split("").map(c => c.charCodeAt(0)));
    const salt = new Uint8Array(atob(saltB64).split("").map(c => c.charCodeAt(0)));
    const encryptedData = new Uint8Array(atob(ciphertext).split("").map(c => c.charCodeAt(0)));

    const passwordKey = await window.crypto.subtle.importKey(
        "raw",
        encoder.encode(password),
        { name: "PBKDF2" },
        false,
        ["deriveKey"]
    );

    const encryptionKey = await window.crypto.subtle.deriveKey(
        {
            name: "PBKDF2",
            salt: salt,
            iterations: 100000,
            hash: "SHA-256",
        },
        passwordKey,
        { name: "AES-GCM", length: 256 },
        false,
        ["decrypt"]
    );

    const decryptedContent = await window.crypto.subtle.decrypt(
        { name: "AES-GCM", iv: iv },
        encryptionKey,
        encryptedData
    );

    return new TextDecoder().decode(decryptedContent);
};
