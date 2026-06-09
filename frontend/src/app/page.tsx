import { AppShell } from "@/components/app-shell";
import { getHealth, getMaterials, getSystemStatus } from "@/lib/api";

export default async function Home() {
  const [health, status, materials] = await Promise.all([
    getHealth(),
    getSystemStatus(),
    getMaterials(),
  ]);

  return <AppShell health={health} materials={materials.materials} status={status} />;
}
