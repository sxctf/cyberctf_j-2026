export {};

declare module "*.glb";
declare module "*.png";

declare module "meshline" {
  export const MeshLineGeometry: new () => MeshLineGeometryInstance;
  export const MeshLineMaterial: new () => MeshLineMaterialInstance;
}

interface MeshLineGeometryInstance {
  new (): {
    setPoints(...args: unknown[]): void;
    setLinearDensity(...args: unknown[]): void;
    setWorldDistance(...args: unknown[]): void;
  };
}

interface MeshLineMaterialInstance {
  new (): {
    map: unknown;
    transparent: boolean;
    side: unknown;
  };
}

declare global {
  namespace JSX {
    interface IntrinsicElements {
      meshLineGeometry: Record<string, unknown>;
      meshLineMaterial: Record<string, unknown>;
    }
  }
}
