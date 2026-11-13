//! Native live fall detection: preprocessing, ONNX Runtime sessions, scheduling and coordination.

use serde_json::Value;
use std::collections::BTreeSet;

pub mod backend;
pub mod bundle;
pub mod feed;
pub mod preprocessing;
pub mod records;
pub mod runtime;
pub mod scheduler;
pub mod sequence;
pub mod stream;
pub mod window;
pub mod worker;

/// Audit an ONNX Runtime Chrome trace against an explicit CPU operation allowlist.
///
/// Reject missing placement evidence, unknown providers, and any CPU operation
/// that the caller has not reviewed. This audits placement only, not correctness
/// or adapter identity; a passing trace alone cannot qualify a deployment.
pub fn audit_placement(
    trace: &Value,
    allowed_cpu_ops: &BTreeSet<String>,
) -> Result<Placement, String> {
    let events = trace
        .as_array()
        .or_else(|| trace.get("traceEvents").and_then(Value::as_array))
        .ok_or("profile must contain an event array")?;
    let mut placement = Placement::default();
    for event in events {
        if event.get("cat").and_then(Value::as_str) != Some("Node") {
            continue;
        }
        let args = &event["args"];
        // Fence and scheduling events do not identify executed kernels.
        let Some(provider) = args.get("provider").and_then(Value::as_str) else {
            if event["name"]
                .as_str()
                .is_some_and(|n| n.ends_with("_kernel_time"))
            {
                return Err("kernel event lacks provider evidence".into());
            }
            continue;
        };
        let op = args
            .get("op_name")
            .and_then(Value::as_str)
            .filter(|op| !op.is_empty())
            .ok_or("kernel event lacks operator identity")?;
        match provider {
            "WebGpuExecutionProvider" | "WebGPUExecutionProvider" => {
                placement.webgpu_ops.insert(op.to_owned());
                placement.webgpu_kernels += 1;
            }
            "CPUExecutionProvider" if allowed_cpu_ops.contains(op) => {
                for key in ["input_type_shape", "output_type_shape"] {
                    let shapes = args[key]
                        .as_array()
                        .ok_or("CPU allowance lacks tensor type evidence")?;
                    if shapes.is_empty()
                        || shapes.iter().any(|shape| {
                            shape.as_object().is_none_or(|types| {
                                types.is_empty()
                                    || types.keys().any(|ty| {
                                        !["int64", "int32", "bool"].contains(&ty.as_str())
                                    })
                            })
                        })
                    {
                        return Err(format!(
                            "CPU operation is not proven integer/bool control work: {op}"
                        ));
                    }
                }
                placement.cpu_ops.insert(op.to_owned());
            }
            "CPUExecutionProvider" => return Err(format!("unapproved CPU operation: {op}")),
            _ => return Err(format!("unexpected provider: {provider}")),
        }
    }
    if placement.webgpu_kernels == 0 {
        return Err("no WebGPU kernel execution evidence".into());
    }
    Ok(placement)
}

/// Observed operations, retained for a human-reviewed qualification report.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct Placement {
    pub webgpu_ops: BTreeSet<String>,
    pub cpu_ops: BTreeSet<String>,
    pub webgpu_kernels: usize,
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn cpu_allowlist_cannot_authorize_float_neural_computation() {
        let trace = json!([
            {"cat":"Node","args":{"provider":"WebGpuExecutionProvider","op_name":"Conv"}},
            {"cat":"Node","args":{"provider":"CPUExecutionProvider","op_name":"Gemm",
                "input_type_shape":[{"float":[1,32]}],"output_type_shape":[{"float":[1]}]}}
        ]);
        assert!(audit_placement(&trace, &BTreeSet::from(["Gemm".into()])).is_err());
    }

    #[test]
    fn rejects_empty_and_cpu_fallback() {
        assert!(audit_placement(&json!([]), &BTreeSet::new()).is_err());
        let trace = json!([{"cat":"Node","args": {
            "provider":"CPUExecutionProvider", "op_name":"LSTM"
        }}]);
        assert!(audit_placement(&trace, &BTreeSet::new()).is_err());
    }

    #[test]
    fn records_explicit_control_allowance() {
        let trace = json!([
            {"cat":"Node","args":{"provider":"WebGpuExecutionProvider","op_name":"Conv"}},
            {"cat":"Node","args":{"provider":"CPUExecutionProvider","op_name":"Shape",
            "input_type_shape":[{"int64":[1]}],"output_type_shape":[{"int64":[1]}]}}
        ]);
        let report = audit_placement(&trace, &BTreeSet::from(["Shape".into()])).unwrap();
        assert_eq!(report.webgpu_kernels, 1);
        assert!(report.cpu_ops.contains("Shape"));
    }
}
