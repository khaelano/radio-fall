//! Leading eigenvectors of a small dense symmetric matrix.
//!
//! Householder reduction to tridiagonal form in float32 (AVX2 and FMA when
//! available, two rows per pass), bisection of all requested eigenvalues in
//! lockstep and inverse iteration on the tridiagonal matrix in float64, and
//! back-transformation of the requested vectors only. This is the structure of
//! LAPACK's `ssyevr` with a subset of eigenvectors, specialized for matrices
//! that fit in cache (the PC-spectrum front end uses 238 x 238).

/// Most eigenvectors one call can return.
pub const MAX_VECTORS: usize = 8;

/// Scratch memory for one matrix size, reused between calls.
pub struct Workspace {
    n: usize,
    stride: usize,
    /// Row-major matrix; the caller fills the lower triangle, which is destroyed.
    pub matrix: Vec<f32>,
    reflectors: Vec<f32>,
    tau: Vec<f32>,
    pub(crate) diagonal: Vec<f64>,
    pub(crate) off: Vec<f64>,
    squares: Vec<f64>,
    column: Vec<f32>,
    p: Vec<f32>,
    extra: Vec<f32>,
    w: Vec<f32>,
    vector: Vec<f64>,
    lower: Vec<f64>,
    inverse: Vec<f64>,
    upper: Vec<f64>,
    upper2: Vec<f64>,
    pivot: Vec<bool>,
}

impl Workspace {
    /// Workspace for `n x n` matrices with rows `stride` floats apart.
    pub fn new(n: usize, stride: usize) -> Self {
        assert!(n >= 3 && stride >= n);
        Self {
            n,
            stride,
            matrix: vec![0.0; n * stride],
            reflectors: vec![0.0; n * stride],
            tau: vec![0.0; n],
            diagonal: vec![0.0; n],
            off: vec![0.0; n],
            squares: vec![0.0; n],
            column: vec![0.0; n],
            // Eight floats of padding: the pass updates p with full-width tails.
            p: vec![0.0; stride + 8],
            extra: vec![0.0; stride],
            w: vec![0.0; stride],
            vector: vec![0.0; n],
            lower: vec![0.0; n],
            inverse: vec![0.0; n],
            upper: vec![0.0; n],
            upper2: vec![0.0; n],
            pivot: vec![false; n],
        }
    }

    /// Matrix order.
    pub fn n(&self) -> usize {
        self.n
    }

    /// Row stride of [`Workspace::matrix`] and of the output vectors.
    pub fn stride(&self) -> usize {
        self.stride
    }
}

/// Whether the AVX2 and FMA kernels can run on this processor.
pub fn simd_available() -> bool {
    #[cfg(target_arch = "x86_64")]
    {
        std::is_x86_feature_detected!("avx2") && std::is_x86_feature_detected!("fma")
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        false
    }
}

/// Eigenvectors of the `k` largest eigenvalues of the symmetric matrix whose
/// lower triangle is in `workspace.matrix` (destroyed).
///
/// `out` receives `k` rows of `stride` floats (entries past `n` are zeroed), in
/// descending eigenvalue order; eigenvalues are returned in the same order.
/// Signs are arbitrary. `simd` selects the AVX2 kernels when available.
pub fn leading(workspace: &mut Workspace, k: usize, out: &mut [f32], simd: bool) -> Vec<f64> {
    let (n, stride) = (workspace.n, workspace.stride);
    assert!((1..=MAX_VECTORS).contains(&k) && k <= n && out.len() >= k * stride);
    let simd = simd && simd_available();
    tridiagonalize(workspace, simd);
    let values = largest_eigenvalues(workspace, k);
    for (index, &value) in values.iter().enumerate() {
        tridiagonal_vector(workspace, value, index, out);
    }
    back_transform(workspace, out, k, simd);
    values
}

pub(crate) fn tridiagonalize(ws: &mut Workspace, simd: bool) {
    let (n, s) = (ws.n, ws.stride);
    // ws.column[i] holds the current A[i][c] of the column c being reduced. It is
    // read down the matrix only for c = 0 and 1; afterwards each pass captures it
    // while the row is in cache (a column read in row-major storage touches one
    // cache line per element).
    for i in 0..n {
        ws.column[i] = ws.matrix[i * s];
    }
    let mut has = householder(ws, 0);
    if has {
        // Step 0's product over rows and columns 1..; captures column 1.
        ws.p[1..n].fill(0.0);
        pass(ws, 1, false, true, simd);
        finish_w(ws, 0);
    } else {
        for i in 1..n {
            ws.column[i] = ws.matrix[i * s + 1];
        }
    }
    for k in 0..n - 2 {
        let base = k + 1;
        // Column `base` takes step k's update first, so step k + 1's reflector is
        // known before the pass that applies step k to the rest of the matrix.
        if has {
            let v = &ws.reflectors[k * s..(k + 1) * s];
            let (vb, wb) = (v[base], ws.w[base]);
            for ((value, &vi), &wi) in ws.column[base..n]
                .iter_mut()
                .zip(&v[base..n])
                .zip(&ws.w[base..n])
            {
                *value -= vi * wb + wi * vb;
            }
        }
        if k + 1 == n - 2 {
            // Last 2 x 2 block: no reflector; apply step k to A[n-1][n-1].
            ws.diagonal[n - 2] = f64::from(ws.column[n - 2]);
            ws.off[n - 2] = f64::from(ws.column[n - 1]);
            let mut last = ws.matrix[(n - 1) * s + n - 1];
            if has {
                let v = &ws.reflectors[k * s..(k + 1) * s];
                last -= 2.0 * v[n - 1] * ws.w[n - 1];
            }
            ws.diagonal[n - 1] = f64::from(last);
            break;
        }
        let next = householder(ws, k + 1);
        if next {
            ws.p[base + 1..n].fill(0.0);
        }
        // One pass over rows and columns base + 1..: step k's rank-2 update, and
        // with the updated values step k + 1's product p = A22 v.
        pass(ws, k + 2, has, next, simd);
        if next {
            finish_w(ws, k + 1);
        }
        has = next;
    }
}

/// Reflector of step `k` from `ws.column[k..n]` (column k, rows k..n); sets the
/// diagonal and off-diagonal entries; false if the column is already reduced.
fn householder(ws: &mut Workspace, k: usize) -> bool {
    let (n, s) = (ws.n, ws.stride);
    let base = k + 1;
    ws.diagonal[k] = f64::from(ws.column[k]);
    let alpha = f64::from(ws.column[base]);
    let mut sigma = 0.0f64;
    for &value in &ws.column[base + 1..n] {
        let x = f64::from(value);
        sigma += x * x;
    }
    if sigma == 0.0 {
        ws.off[k] = alpha;
        ws.tau[k] = 0.0;
        return false;
    }
    let beta = -alpha.signum() * (alpha * alpha + sigma).sqrt();
    let tau = (beta - alpha) / beta;
    let scale = 1.0 / (alpha - beta);
    ws.off[k] = beta;
    ws.tau[k] = tau as f32;
    let v = &mut ws.reflectors[k * s..(k + 1) * s];
    v[base] = 1.0;
    for (target, &value) in v[base + 1..n].iter_mut().zip(&ws.column[base + 1..n]) {
        *target = (f64::from(value) * scale) as f32;
    }
    true
}

/// `p *= tau`, then `w = p - (tau / 2) (p . v) v` for step `k`.
fn finish_w(ws: &mut Workspace, k: usize) {
    let (n, s) = (ws.n, ws.stride);
    let base = k + 1;
    let tau = f64::from(ws.tau[k]);
    let tau32 = ws.tau[k];
    let v = &ws.reflectors[k * s..(k + 1) * s];
    let mut pv = 0.0f64;
    for (p, &vi) in ws.p[base..n].iter_mut().zip(&v[base..n]) {
        *p *= tau32;
        pv += f64::from(*p) * f64::from(vi);
    }
    let gamma = (0.5 * tau * pv) as f32;
    for ((w, &p), &vi) in ws.w[base..n]
        .iter_mut()
        .zip(&ws.p[base..n])
        .zip(&v[base..n])
    {
        *w = p - gamma * vi;
    }
}

/// Rows and columns `c..n` (lower triangle): with `update`, subtract step
/// `c - 2`'s `v w^T + w v^T`; with `product`, add the updated rows' share of
/// step `c - 1`'s `A22 v` to `ws.p`. Captures each row's updated column `c`.
fn pass(ws: &mut Workspace, c: usize, update: bool, product: bool, simd: bool) {
    let (n, s) = (ws.n, ws.stride);
    #[cfg(target_arch = "x86_64")]
    if simd {
        assert!(c >= 1 && (!update || c >= 2) && c <= n);
        // Unused operands point at valid memory and are never read.
        let v = if update {
            ws.reflectors[(c - 2) * s..].as_ptr()
        } else {
            ws.w.as_ptr()
        };
        let next = if product {
            ws.reflectors[(c - 1) * s..].as_ptr()
        } else {
            ws.w.as_ptr()
        };
        if product {
            ws.extra[c..n].fill(0.0);
        }
        let args = (
            ws.matrix.as_mut_ptr(),
            s,
            c,
            n,
            v,
            ws.w.as_ptr(),
            next,
            ws.p.as_mut_ptr(),
            ws.extra.as_mut_ptr(),
            ws.column.as_mut_ptr(),
        );
        // SAFETY: AVX2 and FMA were detected; the matrix holds n rows of s floats,
        // reflector rows, w, p and column hold at least n floats, and the pass only
        // touches rows and columns c..n of the lower triangle.
        unsafe {
            match (update, product) {
                (true, true) => avx::pass::<true, true>(args),
                (true, false) => avx::pass::<true, false>(args),
                (false, true) => avx::pass::<false, true>(args),
                (false, false) => avx::pass::<false, false>(args),
            }
        }
        if product {
            for i in c..n {
                ws.p[i] += ws.extra[i];
            }
        }
        return;
    }
    let _ = simd;
    let empty: &[f32] = &[];
    let (v, w) = if update {
        (&ws.reflectors[(c - 2) * s..(c - 1) * s], &ws.w[..])
    } else {
        (empty, empty)
    };
    let next = if product {
        &ws.reflectors[(c - 1) * s..c * s]
    } else {
        empty
    };
    let upd = |row: usize, col: usize| {
        if update {
            v[row] * w[col] + w[row] * v[col]
        } else {
            0.0
        }
    };
    let mut i = c;
    while i + 1 < n {
        let length = i - c;
        let (top, bottom) = ws.matrix.split_at_mut((i + 1) * s);
        let a = &mut top[i * s + c..i * s + i + 1];
        let b = &mut bottom[c..i + 2];
        let (da, db) = pair(
            a,
            b,
            v.get(c..i).unwrap_or(empty),
            w.get(c..i).unwrap_or(empty),
            next.get(c..i).unwrap_or(empty),
            &mut ws.p[c..i],
            length,
            if update {
                [v[i], w[i], v[i + 1], w[i + 1]]
            } else {
                [0.0; 4]
            },
            if product {
                [next[i], next[i + 1]]
            } else {
                [0.0; 2]
            },
        );
        a[length] -= upd(i, i);
        b[length] -= upd(i + 1, i);
        b[length + 1] -= upd(i + 1, i + 1);
        if product {
            let (aii, bi, bj) = (a[length], b[length], b[length + 1]);
            ws.p[i] += da + aii * next[i] + bi * next[i + 1];
            ws.p[i + 1] += db + bi * next[i] + bj * next[i + 1];
        }
        ws.column[i] = a[0];
        ws.column[i + 1] = b[0];
        i += 2;
    }
    if i < n {
        let length = i - c;
        let a = &mut ws.matrix[i * s + c..i * s + i + 1];
        let da = single(
            a,
            v.get(c..i).unwrap_or(empty),
            w.get(c..i).unwrap_or(empty),
            next.get(c..i).unwrap_or(empty),
            &mut ws.p[c..i],
            length,
            if update { [v[i], w[i]] } else { [0.0; 2] },
            if product { next[i] } else { 0.0 },
        );
        a[length] -= upd(i, i);
        if product {
            ws.p[i] += da + a[length] * next[i];
        }
        ws.column[i] = a[0];
    }
}

/// Scalar path: two rows over `length` shared columns: optional rank-2 update
/// (`v`, `w`, `scalars = [va, wa, vb, wb]`, empty slices to skip), then optional
/// product with `next` (`nexts = [next_a, next_b]`, empty slice to skip): returns
/// the rows' dot products with `next` and adds `next_a a + next_b b` to `p`.
#[allow(clippy::too_many_arguments)]
fn pair(
    a: &mut [f32],
    b: &mut [f32],
    v: &[f32],
    w: &[f32],
    next: &[f32],
    p: &mut [f32],
    length: usize,
    scalars: [f32; 4],
    nexts: [f32; 2],
) -> (f32, f32) {
    let (update, product) = (!v.is_empty(), !next.is_empty());
    let [va, wa, vb, wb] = scalars;
    let (mut da, mut db) = (0.0f32, 0.0f32);
    for j in 0..length {
        if update {
            a[j] -= va * w[j] + wa * v[j];
            b[j] -= vb * w[j] + wb * v[j];
        }
        if product {
            da += a[j] * next[j];
            db += b[j] * next[j];
            p[j] += nexts[0] * a[j] + nexts[1] * b[j];
        }
    }
    (da, db)
}

/// One-row form of [`pair`].
#[allow(clippy::too_many_arguments)]
fn single(
    a: &mut [f32],
    v: &[f32],
    w: &[f32],
    next: &[f32],
    p: &mut [f32],
    length: usize,
    scalars: [f32; 2],
    next_a: f32,
) -> f32 {
    let (update, product) = (!v.is_empty(), !next.is_empty());
    let mut da = 0.0f32;
    for j in 0..length {
        if update {
            a[j] -= scalars[0] * w[j] + scalars[1] * v[j];
        }
        if product {
            da += a[j] * next[j];
            p[j] += next_a * a[j];
        }
    }
    da
}

/// Eigenvalues below each of `x` (Sturm sequences, all lanes in one sweep, so
/// the divisions of different lanes overlap).
fn count_below<const L: usize>(
    diagonal: &[f64],
    squares: &[f64],
    x: &[f64; L],
    pivmin: f64,
) -> [f64; L] {
    let mut q = [0.0f64; L];
    let mut count = [0.0f64; L];
    for l in 0..L {
        let mut t = diagonal[0] - x[l];
        if t.abs() < pivmin {
            t = -pivmin;
        }
        q[l] = t;
        count[l] = if t < 0.0 { 1.0 } else { 0.0 };
    }
    for i in 1..diagonal.len() {
        let (d, e2) = (diagonal[i], squares[i - 1]);
        for l in 0..L {
            let mut t = d - x[l] - e2 / q[l];
            if t.abs() < pivmin {
                t = -pivmin;
            }
            q[l] = t;
            count[l] += if t < 0.0 { 1.0 } else { 0.0 };
        }
    }
    count
}

/// The `k` largest eigenvalues, descending, by bisection to `1e-12` of the
/// matrix norm (inverse iteration then converges in a few steps).
pub(crate) fn largest_eigenvalues(ws: &mut Workspace, k: usize) -> Vec<f64> {
    match k {
        1 => bisect::<1>(ws),
        2 => bisect::<2>(ws),
        3 => bisect::<3>(ws),
        4 => bisect::<4>(ws),
        5 => bisect::<5>(ws),
        6 => bisect::<6>(ws),
        7 => bisect::<7>(ws),
        _ => bisect::<MAX_VECTORS>(ws)[..k].to_vec(),
    }
}

/// [`largest_eigenvalues`] with one bisection lane per eigenvalue.
fn bisect<const K: usize>(ws: &mut Workspace) -> Vec<f64> {
    let n = ws.n;
    let (diagonal, off) = (&ws.diagonal[..n], &ws.off[..n - 1]);
    let (mut low, mut high) = (f64::INFINITY, f64::NEG_INFINITY);
    let mut largest_off = 0.0f64;
    for i in 0..n {
        let left = if i > 0 { off[i - 1].abs() } else { 0.0 };
        let right = if i + 1 < n { off[i].abs() } else { 0.0 };
        low = low.min(diagonal[i] - left - right);
        high = high.max(diagonal[i] + left + right);
        if i + 1 < n {
            ws.squares[i] = off[i] * off[i];
            largest_off = largest_off.max(ws.squares[i]);
        }
    }
    let norm = low.abs().max(high.abs()).max(f64::MIN_POSITIVE);
    let pivmin = f64::MIN_POSITIVE * largest_off.max(1.0);
    let margin = 2.0 * f64::EPSILON * norm * n as f64 + 2.0 * pivmin;
    low -= margin;
    high += margin;
    let tolerance = 1e-12 * norm + pivmin;
    let steps = ((high - low) / tolerance).log2().ceil().max(1.0) as usize;
    let mut targets = [0.0f64; K];
    for (l, target) in targets.iter_mut().enumerate() {
        *target = n.saturating_sub(1 + l) as f64; // ascending index of the l-th largest
    }
    let (mut a, mut b) = ([low; K], [high; K]);
    for _ in 0..steps {
        let mut middle = [0.0f64; K];
        for l in 0..K {
            middle[l] = 0.5 * (a[l] + b[l]);
        }
        let counts = count_below(diagonal, &ws.squares[..n - 1], &middle, pivmin);
        for l in 0..K {
            if counts[l] > targets[l] {
                b[l] = middle[l];
            } else {
                a[l] = middle[l];
            }
        }
    }
    (0..K).map(|l| 0.5 * (a[l] + b[l])).collect()
}

/// Eigenvector of the tridiagonal matrix for `value` by inverse iteration,
/// orthogonalized against the vectors already in `out` (rows `0..index`).
pub(crate) fn tridiagonal_vector(ws: &mut Workspace, value: f64, index: usize, out: &mut [f32]) {
    let (n, s) = (ws.n, ws.stride);
    let mut norm = 0.0f64;
    for i in 0..n {
        let left = if i > 0 { ws.off[i - 1].abs() } else { 0.0 };
        let right = if i + 1 < n { ws.off[i].abs() } else { 0.0 };
        norm = norm.max(ws.diagonal[i].abs() + left + right);
    }
    let tiny = f64::EPSILON * norm.max(f64::MIN_POSITIVE);
    // LU factorization of T - value I with partial pivoting (LAPACK dgttrf);
    // pivots smaller than eps * norm are replaced, as inverse iteration needs.
    let main = &mut ws.inverse;
    for (target, &d) in main.iter_mut().zip(&ws.diagonal) {
        *target = d - value;
    }
    for i in 0..n - 1 {
        ws.lower[i] = ws.off[i];
        ws.upper[i] = ws.off[i];
    }
    for i in 0..n - 1 {
        ws.upper2[i] = 0.0;
        if main[i].abs() >= ws.lower[i].abs() {
            ws.pivot[i] = false;
            if main[i].abs() < tiny {
                main[i] = if main[i] < 0.0 { -tiny } else { tiny };
            }
            let factor = ws.lower[i] / main[i];
            ws.lower[i] = factor;
            main[i + 1] -= factor * ws.upper[i];
        } else {
            ws.pivot[i] = true;
            let factor = main[i] / ws.lower[i];
            main[i] = ws.lower[i];
            ws.lower[i] = factor;
            let temp = ws.upper[i];
            ws.upper[i] = main[i + 1];
            main[i + 1] = temp - factor * main[i + 1];
            if i + 2 < n {
                ws.upper2[i] = ws.upper[i + 1];
                ws.upper[i + 1] *= -factor;
            }
        }
    }
    if main[n - 1].abs() < tiny {
        main[n - 1] = if main[n - 1] < 0.0 { -tiny } else { tiny };
    }
    for value in main.iter_mut() {
        *value = 1.0 / *value; // reciprocal pivots: substitution multiplies
    }
    let inverse = &ws.inverse;
    // Deterministic start with every component nonzero.
    let y = &mut ws.vector;
    for (i, value) in y.iter_mut().enumerate() {
        *value = 1.0 + ((i * 7919 + index * 104_729) % 97) as f64 / 97.0;
    }
    // The eigenvalue is accurate to 1e-12 of the norm, so one solve already
    // converges for any separated eigenvalue; the second, after orthogonalizing,
    // settles clusters.
    for _ in 0..2 {
        for i in 0..n - 1 {
            if ws.pivot[i] {
                let temp = y[i];
                y[i] = y[i + 1];
                y[i + 1] = temp - ws.lower[i] * y[i];
            } else {
                y[i + 1] -= ws.lower[i] * y[i];
            }
        }
        y[n - 1] *= inverse[n - 1];
        y[n - 2] = (y[n - 2] - ws.upper[n - 2] * y[n - 1]) * inverse[n - 2];
        for i in (0..n - 2).rev() {
            y[i] = (y[i] - ws.upper[i] * y[i + 1] - ws.upper2[i] * y[i + 2]) * inverse[i];
        }
        for previous in 0..index {
            let row = &out[previous * s..previous * s + n];
            let dot: f64 = row
                .iter()
                .zip(y.iter())
                .map(|(&a, &b)| f64::from(a) * b)
                .sum();
            for (value, &a) in y.iter_mut().zip(row) {
                *value -= dot * f64::from(a);
            }
        }
        let length = y.iter().map(|v| v * v).sum::<f64>().sqrt();
        let scale = if length > 0.0 { 1.0 / length } else { 0.0 };
        for value in y.iter_mut() {
            *value *= scale;
        }
    }
    let row = &mut out[index * s..(index + 1) * s];
    for (target, &value) in row.iter_mut().zip(y.iter()) {
        // Entries of a unit vector below 1e-30 change nothing but would be
        // subnormal in float32, where every operation on them is microcoded.
        *target = if value.abs() < 1e-30 {
            0.0
        } else {
            value as f32
        };
    }
    row[n..].fill(0.0);
}

/// Apply the reflectors in reverse order to the `k` tridiagonal eigenvectors.
pub(crate) fn back_transform(ws: &Workspace, out: &mut [f32], k: usize, simd: bool) {
    let (n, s) = (ws.n, ws.stride);
    for r in (0..n - 2).rev() {
        let tau = ws.tau[r];
        if tau == 0.0 {
            continue;
        }
        let base = r + 1;
        let v = &ws.reflectors[r * s + base..r * s + n];
        #[cfg(target_arch = "x86_64")]
        if simd {
            // SAFETY: AVX2 and FMA were detected; rows 0..k of out hold s floats
            // each, and base + v.len() == n <= s.
            unsafe { avx::reflect(v.as_ptr(), out.as_mut_ptr().add(base), s, k, v.len(), tau) };
            continue;
        }
        for row in out.chunks_exact_mut(s).take(k) {
            let x = &mut row[base..n];
            let dot: f32 = v.iter().zip(x.iter()).map(|(a, b)| a * b).sum();
            for (target, &value) in x.iter_mut().zip(v) {
                *target -= tau * dot * value;
            }
        }
    }
}

#[cfg(target_arch = "x86_64")]
pub(crate) mod avx {
    use super::MAX_VECTORS;
    use std::arch::x86_64::*;

    static MASKS: [i32; 16] = [-1, -1, -1, -1, -1, -1, -1, -1, 0, 0, 0, 0, 0, 0, 0, 0];

    /// Lane mask selecting the first `count` (1-7) of eight lanes.
    #[inline]
    #[target_feature(enable = "avx2,fma")]
    pub(crate) unsafe fn mask(count: usize) -> __m256i {
        // SAFETY: 8 - count is in 1..=7, so 8 integers are readable.
        unsafe { _mm256_loadu_si256(MASKS.as_ptr().add(8 - count).cast()) }
    }

    /// Horizontal sum of eight lanes.
    #[inline]
    #[target_feature(enable = "avx2,fma")]
    pub(crate) unsafe fn sum(v: __m256) -> f32 {
        let low = _mm256_castps256_ps128(v);
        let high = _mm256_extractf128_ps::<1>(v);
        let pair = _mm_add_ps(low, high);
        let pair = _mm_add_ps(pair, _mm_movehl_ps(pair, pair));
        _mm_cvtss_f32(_mm_add_ss(pair, _mm_shuffle_ps::<1>(pair, pair)))
    }

    /// Operands of [`pass`]: matrix, stride, first column c, order n, update
    /// vectors v and w, next reflector, product accumulator p, column capture.
    pub(crate) type PassArgs = (
        *mut f32,
        usize,
        usize,
        usize,
        *const f32,
        *const f32,
        *const f32,
        *mut f32,
        *mut f32,
        *mut f32,
    );

    /// One pass over rows and columns `c..n` of the lower triangle, two rows at
    /// a time: with `UPDATE`, `A -= v w^T + w v^T`; with `PRODUCT`, the updated
    /// rows' share of `p = A next` (row dot products into `p[i]`, mirrored column
    /// multiples into `p[c..i]`). Writes each row's updated `A[i][c]` to `column[i]`.
    ///
    /// During the pass `p` receives full-width vector stores only (the rows'
    /// diagonal-end contributions go to `extra`, added afterwards): a wide load
    /// over a narrower recent store cannot be forwarded and would stall every
    /// row pair. Tails read and write `p` at full width with zero added in the
    /// lanes past the row, so `p` needs 8 floats beyond `n`.
    #[target_feature(enable = "avx2,fma")]
    pub(crate) unsafe fn pass<const UPDATE: bool, const PRODUCT: bool>(args: PassArgs) {
        let (matrix, s, c, n, v, w, next, p, extra, column) = args;
        // SAFETY: the caller guarantees n rows of s floats behind matrix, n + 8
        // floats behind p and n behind v, w, next, extra and column (unused ones
        // are never read).
        unsafe {
            let update = |row: usize, col: usize| -> f32 {
                if UPDATE {
                    *v.add(row) * *w.add(col) + *w.add(row) * *v.add(col)
                } else {
                    0.0
                }
            };
            let (vc, wc, nc, pc) = (
                v.wrapping_add(c),
                w.wrapping_add(c),
                next.wrapping_add(c),
                p.add(c),
            );
            let mut i = c;
            while i + 1 < n {
                let length = i - c;
                let (a, b) = (matrix.add(i * s + c), matrix.add((i + 1) * s + c));
                let (sva, swa, svb, swb) = if UPDATE {
                    (
                        _mm256_set1_ps(*v.add(i)),
                        _mm256_set1_ps(*w.add(i)),
                        _mm256_set1_ps(*v.add(i + 1)),
                        _mm256_set1_ps(*w.add(i + 1)),
                    )
                } else {
                    (
                        _mm256_setzero_ps(),
                        _mm256_setzero_ps(),
                        _mm256_setzero_ps(),
                        _mm256_setzero_ps(),
                    )
                };
                let (na, nb) = if PRODUCT {
                    (*next.add(i), *next.add(i + 1))
                } else {
                    (0.0, 0.0)
                };
                let (sna, snb) = (_mm256_set1_ps(na), _mm256_set1_ps(nb));
                let (mut da, mut db) = (_mm256_setzero_ps(), _mm256_setzero_ps());
                let mut chunk = |j: usize, m: Option<__m256i>| {
                    let load = |ptr: *const f32| match m {
                        Some(m) => _mm256_maskload_ps(ptr, m),
                        None => _mm256_loadu_ps(ptr),
                    };
                    let store = |ptr: *mut f32, value: __m256| match m {
                        Some(m) => _mm256_maskstore_ps(ptr, m, value),
                        None => _mm256_storeu_ps(ptr, value),
                    };
                    let (mut ra, mut rb) = (load(a.add(j)), load(b.add(j)));
                    if UPDATE {
                        let (x, y) = (load(vc.add(j)), load(wc.add(j)));
                        ra = _mm256_fnmadd_ps(swa, x, _mm256_fnmadd_ps(sva, y, ra));
                        rb = _mm256_fnmadd_ps(swb, x, _mm256_fnmadd_ps(svb, y, rb));
                        store(a.add(j), ra);
                        store(b.add(j), rb);
                    }
                    if PRODUCT {
                        // Past the row, ra and rb are zero (masked loads), so the
                        // full-width update of p leaves those lanes unchanged.
                        let z = load(nc.add(j));
                        da = _mm256_fmadd_ps(ra, z, da);
                        db = _mm256_fmadd_ps(rb, z, db);
                        let q = _mm256_fmadd_ps(
                            snb,
                            rb,
                            _mm256_fmadd_ps(sna, ra, _mm256_loadu_ps(pc.add(j))),
                        );
                        _mm256_storeu_ps(pc.add(j), q);
                    }
                };
                let mut j = 0;
                while j + 8 <= length {
                    chunk(j, None);
                    j += 8;
                }
                if j < length {
                    chunk(j, Some(mask(length - j)));
                }
                let aii = *a.add(length) - update(i, i);
                let bi = *b.add(length) - update(i + 1, i);
                let bj = *b.add(length + 1) - update(i + 1, i + 1);
                *a.add(length) = aii;
                *b.add(length) = bi;
                *b.add(length + 1) = bj;
                if PRODUCT {
                    *extra.add(i) += sum(da) + aii * na + bi * nb;
                    *extra.add(i + 1) += sum(db) + bi * na + bj * nb;
                }
                *column.add(i) = *a;
                *column.add(i + 1) = *b;
                i += 2;
            }
            if i < n {
                let length = i - c;
                let a = matrix.add(i * s + c);
                let (sva, swa) = if UPDATE {
                    (_mm256_set1_ps(*v.add(i)), _mm256_set1_ps(*w.add(i)))
                } else {
                    (_mm256_setzero_ps(), _mm256_setzero_ps())
                };
                let na = if PRODUCT { *next.add(i) } else { 0.0 };
                let sna = _mm256_set1_ps(na);
                let mut da = _mm256_setzero_ps();
                let mut chunk = |j: usize, m: Option<__m256i>| {
                    let load = |ptr: *const f32| match m {
                        Some(m) => _mm256_maskload_ps(ptr, m),
                        None => _mm256_loadu_ps(ptr),
                    };
                    let store = |ptr: *mut f32, value: __m256| match m {
                        Some(m) => _mm256_maskstore_ps(ptr, m, value),
                        None => _mm256_storeu_ps(ptr, value),
                    };
                    let mut ra = load(a.add(j));
                    if UPDATE {
                        let (x, y) = (load(vc.add(j)), load(wc.add(j)));
                        ra = _mm256_fnmadd_ps(swa, x, _mm256_fnmadd_ps(sva, y, ra));
                        store(a.add(j), ra);
                    }
                    if PRODUCT {
                        da = _mm256_fmadd_ps(ra, load(nc.add(j)), da);
                        _mm256_storeu_ps(
                            pc.add(j),
                            _mm256_fmadd_ps(sna, ra, _mm256_loadu_ps(pc.add(j))),
                        );
                    }
                };
                let mut j = 0;
                while j + 8 <= length {
                    chunk(j, None);
                    j += 8;
                }
                if j < length {
                    chunk(j, Some(mask(length - j)));
                }
                let aii = *a.add(length) - update(i, i);
                *a.add(length) = aii;
                if PRODUCT {
                    *extra.add(i) += sum(da) + aii * na;
                }
                *column.add(i) = *a;
            }
        }
    }

    /// Apply `I - tau v v^T` to the `K` vectors `x + r * stride` over `..n`,
    /// loading `v` once per pass for all of them.
    #[target_feature(enable = "avx2,fma")]
    pub(crate) unsafe fn reflect_rows<const K: usize>(
        v: *const f32,
        x: *mut f32,
        stride: usize,
        n: usize,
        tau: f32,
    ) {
        // SAFETY: the caller guarantees n floats behind v and behind each of the
        // K rows x + r * stride.
        unsafe {
            let mut acc = [_mm256_setzero_ps(); K];
            let mut j = 0;
            while j + 8 <= n {
                let value = _mm256_loadu_ps(v.add(j));
                for (r, total) in acc.iter_mut().enumerate() {
                    *total = _mm256_fmadd_ps(value, _mm256_loadu_ps(x.add(r * stride + j)), *total);
                }
                j += 8;
            }
            let tail = if j < n { Some(mask(n - j)) } else { None };
            if let Some(m) = tail {
                let value = _mm256_maskload_ps(v.add(j), m);
                for (r, total) in acc.iter_mut().enumerate() {
                    *total = _mm256_fmadd_ps(
                        value,
                        _mm256_maskload_ps(x.add(r * stride + j), m),
                        *total,
                    );
                }
            }
            let mut scale = [_mm256_setzero_ps(); K];
            for (factor, total) in scale.iter_mut().zip(acc) {
                *factor = _mm256_set1_ps(-tau * sum(total));
            }
            let mut j = 0;
            while j + 8 <= n {
                let value = _mm256_loadu_ps(v.add(j));
                for (r, &factor) in scale.iter().enumerate() {
                    let target = x.add(r * stride + j);
                    _mm256_storeu_ps(
                        target,
                        _mm256_fmadd_ps(factor, value, _mm256_loadu_ps(target)),
                    );
                }
                j += 8;
            }
            if let Some(m) = tail {
                let value = _mm256_maskload_ps(v.add(j), m);
                for (r, &factor) in scale.iter().enumerate() {
                    let target = x.add(r * stride + j);
                    _mm256_maskstore_ps(
                        target,
                        m,
                        _mm256_fmadd_ps(factor, value, _mm256_maskload_ps(target, m)),
                    );
                }
            }
        }
    }

    /// [`reflect_rows`] for a runtime count of `1..=MAX_VECTORS` vectors.
    #[target_feature(enable = "avx2,fma")]
    pub(crate) unsafe fn reflect(
        v: *const f32,
        x: *mut f32,
        stride: usize,
        rows: usize,
        n: usize,
        tau: f32,
    ) {
        // SAFETY: forwarded caller guarantees.
        unsafe {
            match rows {
                1 => reflect_rows::<1>(v, x, stride, n, tau),
                2 => reflect_rows::<2>(v, x, stride, n, tau),
                3 => reflect_rows::<3>(v, x, stride, n, tau),
                4 => reflect_rows::<4>(v, x, stride, n, tau),
                5 => reflect_rows::<5>(v, x, stride, n, tau),
                6 => reflect_rows::<6>(v, x, stride, n, tau),
                7 => reflect_rows::<7>(v, x, stride, n, tau),
                _ => reflect_rows::<MAX_VECTORS>(v, x, stride, n, tau),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Symmetric matrix with the given spectrum, rotated by random reflections.
    fn matrix_with_spectrum(spectrum: &[f64], seed: u64) -> Vec<f64> {
        let n = spectrum.len();
        let mut state = seed;
        let mut random = || {
            state = state
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1);
            ((state >> 11) as f64 / (1u64 << 53) as f64) - 0.5
        };
        let mut q = vec![0.0; n * n];
        for i in 0..n {
            q[i * n + i] = 1.0;
        }
        for _ in 0..4 {
            let v: Vec<f64> = (0..n).map(|_| random()).collect();
            let norm: f64 = v.iter().map(|x| x * x).sum();
            for row in 0..n {
                let dot: f64 = (0..n).map(|j| q[row * n + j] * v[j]).sum();
                for j in 0..n {
                    q[row * n + j] -= 2.0 * dot * v[j] / norm;
                }
            }
        }
        let mut a = vec![0.0; n * n];
        for i in 0..n {
            for j in 0..n {
                a[i * n + j] = (0..n)
                    .map(|m| q[i * n + m] * spectrum[m] * q[j * n + m])
                    .sum();
            }
        }
        a
    }

    fn check(n: usize, spectrum: Vec<f64>, simd: bool) {
        let a = matrix_with_spectrum(&spectrum, n as u64 + 3);
        let stride = n.div_ceil(8) * 8;
        let mut ws = Workspace::new(n, stride);
        for i in 0..n {
            for j in 0..=i {
                ws.matrix[i * stride + j] = a[i * n + j] as f32;
            }
        }
        let k = 5;
        let mut out = vec![0.0f32; k * stride];
        let values = leading(&mut ws, k, &mut out, simd);
        let mut sorted = spectrum.clone();
        sorted.sort_by(|x, y| y.partial_cmp(x).unwrap());
        let scale = sorted[0].abs();
        for (value, expected) in values.iter().zip(&sorted) {
            assert!(
                (value - expected).abs() < 1e-5 * scale,
                "{value} vs {expected}"
            );
        }
        for r in 0..k {
            let x = &out[r * stride..r * stride + n];
            let norm: f64 = x.iter().map(|&v| f64::from(v).powi(2)).sum();
            assert!((norm - 1.0).abs() < 1e-5);
            // Residual of A x = lambda x.
            let residual: f64 = (0..n)
                .map(|i| {
                    let ax: f64 = (0..n).map(|j| a[i * n + j] * f64::from(x[j])).sum();
                    (ax - values[r] * f64::from(x[i])).powi(2)
                })
                .sum::<f64>()
                .sqrt();
            assert!(residual < 1e-4 * scale, "residual {residual}");
            for other in 0..r {
                let y = &out[other * stride..other * stride + n];
                let dot: f64 = x
                    .iter()
                    .zip(y)
                    .map(|(&p, &q)| f64::from(p) * f64::from(q))
                    .sum();
                assert!(dot.abs() < 1e-4, "orthogonality {dot}");
            }
        }
    }

    #[test]
    fn leading_vectors_match_a_known_spectrum() {
        for simd in [false, true] {
            for n in [37, 38] {
                // Odd and even orders exercise the unpaired last row.
                let spectrum: Vec<f64> = (0..n).map(|i| 50.0 / (1.0 + i as f64)).collect();
                check(n, spectrum, simd);
            }
        }
    }

    #[test]
    fn close_and_repeated_eigenvalues_give_an_orthonormal_basis() {
        for simd in [false, true] {
            // lambda_5 / lambda_6 = 1.007, the closest ratio seen in the recordings,
            // and a repeated pair inside the five.
            let mut spectrum = vec![40.0, 20.0, 20.0, 8.0, 5.035, 5.0];
            spectrum.extend((0..42).map(|i| 4.0 / (1.0 + i as f64)));
            check(48, spectrum, simd);
        }
    }

    #[test]
    fn zero_matrix_does_not_produce_nan() {
        let mut ws = Workspace::new(20, 24);
        let mut out = vec![0.0f32; 5 * 24];
        let values = leading(&mut ws, 5, &mut out, true);
        assert!(values.iter().all(|v| v.is_finite()));
        assert!(out.iter().all(|v| v.is_finite()));
    }
}
