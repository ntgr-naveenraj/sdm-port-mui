fn main() {
    let target = std::env::var("TARGET").expect("TARGET not set by Cargo");
    println!("cargo:rustc-env=SDM_API_TRIPLE={}", target);
    println!("cargo:rerun-if-changed=binaries");
}
