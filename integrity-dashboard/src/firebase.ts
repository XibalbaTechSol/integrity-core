import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, GithubAuthProvider } from "firebase/auth";

// Real Firebase configuration for 'integrity-protocol-v8'
const firebaseConfig = {
  apiKey: "AIzaSyCaNrGbIPp4EcyLkpTyMS7F7YWosq_woZE",
  authDomain: "integrity-protocol-v8.firebaseapp.com",
  projectId: "integrity-protocol-v8",
  storageBucket: "integrity-protocol-v8.firebasestorage.app",
  messagingSenderId: "489901205272",
  appId: "1:489901205272:web:618478020f9b36ad39206d"
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
export const githubProvider = new GithubAuthProvider();
