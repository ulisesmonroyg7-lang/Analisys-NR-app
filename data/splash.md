# 📘 Metodología – Breather Selection  
*(Splash / Oil Bath Systems)*

---

## 🔢 Datos de entrada
- Geometría del cárter: `(D) Height`, `(D) Width`, `(D) Length`, `(D) Distance from Drain Port to Oil Level`.  
- Capacidad de aceite `(D) Oil Capacity)` si no hay geometría.  
- Temperaturas mín./máx. de operación y ambiente.  
- Factores operacionales: CI, WCCI, RH, Oil Mist, Vibración, Móvil.  
- Espacio disponible `(D) Breather/Fill Port Clearance)`.

---

## 📐 Fórmulas clave
- `V_sump = H × W × L × 0.004329` (gal).  
- `V_oil = H_oil × W × L × 0.004329` (gal).  
- `ΔV_oil = γ × V_oil × ΔT`.  
- `ΔV_air = β × V_air × ΔT`.  
- `CFM_required = (ΔV_total / 7.48) × 1.4`.

---

## 📝 Reglas
1. **Criticidad**: solo A/B requieren breather.  
2. **CFM requerido** → filtra catálogo.  
3. **Operacionales**: CI, WCCI, RH ≥ 75% → Extended Service, Oil Mist, vibración:  
   - `<0.2 ips` → normal  
   - `0.2–0.4 ips` → heavy-duty preferido  
   - `>0.4 ips` → heavy-duty obligatorio  
4. **Capacidad sump vs. Sump Volume MAX**.  
5. **Espacio físico**: altura/diámetro.  
6. **Recomendación**: Óptimo, Modificado (remoto), Sub-óptimo.  

---

## ✅ Flujo simplificado
1. Requiere breather (Criticidad).  
2. Calcular CFM.  
3. Filtrar catálogo por CFM.  
4. Ajustar por ambiente (agua, RH, CI, oil mist, vibración, móvil).  
5. Ajustar por retención de agua (Sump MAX).  
6. Validar espacio.  
7. Recomendar: Óptimo / Modificado / Sub-óptimo.  
