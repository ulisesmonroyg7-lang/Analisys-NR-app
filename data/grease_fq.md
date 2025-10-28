# 📘 Metodología – Breather Selection  
*(Circulating Systems)*

---

## 🔢 Datos de entrada
- Caudal `(D) Flow Rate)` real.  
- Si falta: referencia cruzada a bombas hermanas o estimación por capacidad de aceite.  
- Factores operacionales: CI, WCCI, RH, Oil Mist, vibración.  
- Capacidad `(Circulating/Hyd sump volume max gal.)`.  

---

## 📐 Fórmulas clave
- `CFM_required = (Flow Rate (GPM) / 7.48) × 1.4`.  
- Si no hay GPM → usar expansión térmica (igual que splash).  
- **Margen GPM** = `Breather_Max_GPM / Asset_GPM`.  

---

## 📝 Reglas
1. **Criticidad**: A/B → requieren breather.  
2. **Driver = GPM** si hay dato real/estimado → CFM como chequeo.  
3. **Regla 2.5**: filtrar por `Max Fluid Flow (GPM)` del catálogo (margen ≥1.2 ideal).  
4. **Operacionales**:  
   - RH ≥ 75% o GPM alto (≥25) → forzar Extended Service.  
   - CI, WCCI, Oil Mist, vibración.  
5. **Capacidad sump vs. (Circulating/Hyd) Sump Volume MAX`.  
6. **Espacio físico**.  
7. **Notas específicas**: instalación remota, bypass/check valve, difusor en retorno, espuma.  
8. **Recomendación**: Óptimo, Modificado, Sub-óptimo.  

---

## ✅ Flujo simplificado
1. Requiere breather (Criticidad).  
2. Calcular GPM o estimarlo.  
3. Filtrar catálogo por Max Fluid Flow (margen).  
4. Calcular/verificar CFM (si no hay GPM).  
5. Ajustar por ambiente (agua, RH, CI, oil mist, vibración).  
6. Revisar Sump Volume MAX.  
7. Validar espacio.  
8. Recomendar: Óptimo / Modificado / Sub-óptimo.  
