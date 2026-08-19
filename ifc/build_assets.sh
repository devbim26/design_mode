# Сборка ассетов IFC-вьювера (выполняется один раз при обновлении версий).
#
# Связка версий проверена 19.08.2026:
#   @thatopen/components 3.4.8 + @thatopen/fragments 3.4.7
#   three 0.182.0 + web-ifc 0.0.77 + camera-controls 3.1.2
# Результат (ifc/assets/): thatopen.mjs (бандл esbuild), worker.mjs
# (воркер разбора IFC — по умолчанию качается с unpkg.com, кладём локально),
# web-ifc.wasm (WASM-парсер IFC).
#
# Запуск из корня проекта: bash ifc/build_assets.sh
set -e
cd "$(dirname "$0")/../ifc_assets"

npm install --no-audit --no-fund \
  @thatopen/components@3.4.8 @thatopen/fragments@3.4.7 \
  three@0.182.0 web-ifc@0.0.77 camera-controls@3.1.2

cat > entry.mjs <<'EOF'
export {
  Components, Worlds, SimpleScene, OrthoPerspectiveCamera, SimpleRenderer,
  FragmentsManager, IfcLoader, Hider, Clipper,
} from "@thatopen/components";
export * from "three";
EOF

npm install --no-audit --no-fund --no-save esbuild
npx esbuild entry.mjs --bundle --minify --format=esm --outfile=../ifc/assets/thatopen.mjs
cp node_modules/@thatopen/fragments/dist/worker/worker.mjs ../ifc/assets/worker.mjs
cp node_modules/web-ifc/web-ifc.wasm ../ifc/assets/web-ifc.wasm
ls -la ../ifc/assets/
