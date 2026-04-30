import { Route, Routes } from "react-router-dom";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Sandbox from "@/pages/Sandbox";
import TTS from "@/pages/TTS";
import Vision from "@/pages/Vision";
import Voices from "@/pages/Voices";
import VoiceClone from "@/pages/VoiceClone";
import VoiceDesign from "@/pages/VoiceDesign";
import ASR from "@/pages/ASR";
import AuditLog from "@/pages/AuditLog";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="sandbox" element={<Sandbox />} />
        <Route path="tts" element={<TTS />} />
        <Route path="vision" element={<Vision />} />
        <Route path="voices" element={<Voices />} />
        <Route path="voices/clone" element={<VoiceClone />} />
        <Route path="voices/design" element={<VoiceDesign />} />
        <Route path="asr" element={<ASR />} />
        <Route path="audit" element={<AuditLog />} />
      </Route>
    </Routes>
  );
}
