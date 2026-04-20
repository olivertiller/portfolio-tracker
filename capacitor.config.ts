import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.olivertiller.portefolje",
  appName: "Porteføljerapport",
  webDir: "static",
  server: {
    // Load the app from Railway — UI updates deploy instantly without app update
    url: "https://web-production-96969.up.railway.app",
    cleartext: false,
  },
  plugins: {
    PushNotifications: {
      presentationOptions: ["badge", "sound", "alert"],
    },
    StatusBar: {
      overlaysWebView: false,
      style: "LIGHT",
    },
  },
};

export default config;
