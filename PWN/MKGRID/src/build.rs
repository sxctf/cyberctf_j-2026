// build.rs запускается Cargo до сборки crate.
// Его задача здесь - объяснить линковщику, где лежит C-библиотека и как её подключать.
/// Назначение: настроить линковку с C-библиотекой libctos.so до сборки Rust-кода.
fn main() {
    // CARGO_MANIFEST_DIR = абсолютный путь к корню проекта.
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").expect("manifest dir");

    // Добавляем каталог, в котором линковщик должен искать libctos.so.
    println!("cargo:rustc-link-search=native={manifest_dir}/ctos_lib");
    // Говорим линковщику подключить динамическую библиотеку с именем ctos.
    println!("cargo:rustc-link-lib=dylib=ctos");
    // rpath помогает исполняемому файлу потом найти .so во время запуска.
    println!("cargo:rustc-link-arg=-Wl,-rpath,{manifest_dir}/ctos_lib");
    // Если исходник C изменился, Cargo должен пересобрать проект.
    println!("cargo:rerun-if-changed={manifest_dir}/ctos_lib/libctos.c");
    // То же самое для готовой .so, если ты её обновил вручную.
    println!("cargo:rerun-if-changed={manifest_dir}/ctos_lib/libctos.so");
}
