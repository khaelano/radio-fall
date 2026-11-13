//! Enumerate plugin devices without creating an inference session.
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 2 {
        return Err("usage: probe CORE WEBGPU_PLUGIN".into());
    }
    let environment = ort::init_from(&args[0])?.with_telemetry(false).build()?;
    environment.register_ep_library("webgpu", &args[1])?;
    for device in environment.devices() {
        let hardware = device.hardware_device();
        println!(
            "{}",
            serde_json::json!({"provider":device.ep()?, "vendor":hardware.vendor()?,
            "device_id":hardware.id(), "type":format!("{:?}",hardware.ty())})
        );
    }
    Ok(())
}
