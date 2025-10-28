# 📘 Metodología y Reglas – Breather Selection  
*(Splash / Oil Bath Lubrication Systems)*

---

## 🎯 Objetivo
- Automatizar la selección precisa de breathers con base en cálculos de ingeniería y datos recolectados en campo.  
- Mejorar las recomendaciones técnicas reduciendo tiempo de análisis.  

---

## 📐 Principios metodológicos
- Cálculo de expansión térmica + criterio experto de Noria.  
- Aplica a **gearboxes, bombas, motores eléctricos, rodamientos**.  
- **Sistema:** Splash o Oil Bath lubricado con aceite.  
- **Precisión:** datos duros y calibración iterativa (varios niveles de aceite).  

---

## 🔢 Datos generales

| Dato | Símbolo | Fórmula | Unidades | Fuente | Comentarios |
|------|---------|---------|----------|--------|-------------|
| Coef. expansión aceite | γ | 0.0003611 | 1/°F | Fórmula industrial | |
| Coef. expansión aire | β | 0.001894 | 1/°F | Fórmula industrial | |
| Altura cárter | Sh | – | in | Recolección | `(D) Height` |
| Ancho cárter | Sw | – | in | Recolección | `(D) Width` |
| Largo cárter | Sl | – | in | Recolección | `(D) Length` |
| Altura a nivel de aceite | Shl | – | in | Recolección | `(D) Distance from Drain Port to Oil Level` |
| Volumen sump | V_sump | Sh × Sw × Sl × 0.004329 | gal | Calculado | |
| Volumen aceite | V_oil | Shl × Sw × Sl × 0.004329 | gal | Calculado | Normal capacity `(D) Oil Capacity` |
| Volumen aire | V_air | V_sump – V_oil | gal | Calculado | |

### 🔁 Si solo hay Oil Volume
- Suposición típica: **P_oil = 30%** del volumen total.  
- `V_sump = V_oil / P_oil`  
- `V_air = V_sump – V_oil`

### 🔄 Conversiones de unidad
- Litros → gal: × 0.264172  
- in³ → gal: × 0.004329  
- cm³/min → ft³/min: ÷ 2.8317e4  

---

## 🌡️ Condiciones de operación

| Dato | Símbolo | Fuente | Comentarios |
|------|---------|--------|-------------|
| Temp. ambiente máx. | Max_Amb_temp | Recolección / web | |
| Temp. ambiente mín. | Min_Amb_temp | Recolección / web | |
| Temp. operación máx. | Max_Op_temp | Recolección | `(D) Operating Temperature` |
| Temp. operación mín. | Min_Op_temp | Recolección | `(D) Operating Temperature` |
| ΔT | T_max – T_min | Calculado | Diferencial para expansión |
| Evidencia de oil mist | Oil_vap | Recolección | `(D) Oil Mist Evidence` |
| Contamination Index (CI) | CI | Matriz CI | Bajo / Medio / Alto |
| Contaminant Likelihood | CL | Selección | Low / Medium / Severe / Extreme |
| Humedad relativa | RH | Recolección | `(D) Average Relative Humidity` |
| Water contact cond. | WCC | Recolección | `(D) Water Contact Conditions` |
| Índice de contacto con agua | WCCI | Matriz WCCI | Very Low / Low / Medium / High |
| Vibration | Vib | Recolección | `<0.2 ips / 0.2–0.4 ips / >0.4 ips` |
| Extended service index | ESI | Matriz ESI | None / Disposable / Rebuildable |
| Espacio disponible | AV_Space | Recolección | `(D) Breather/Fill Port Clearance` |
| Criticality | Crit | ORS / análisis cliente | A, B (1 o 2) |

---

## 📈 Cálculo de Expansión Volumétrica

- **ΔT = T_max – T_min**  
- **ΔV_oil = γ × V_oil × ΔT**  
- **ΔV_air = β × V_air × ΔT**  
- **V_total_exp = ΔV_oil + ΔV_air**  
- **CFM requerido = (V_total_exp ÷ 7.48) × Safety factor (1.4 típico)**  

---

## 📊 Tablas de referencia

### 🔹 CI Matrix
| Factor | Contaminant Likelihood |
|--------|------------------------|
| Low    | Low |
| Medium | Medium |
| High   | Severe/Extreme |

### 🔹 WCCI Matrix
| Factor | Condiciones de agua | Desecante requerido |
|--------|---------------------|----------------------|
| Very Low | No water contact, very dry | No |
| Low | No water contact, typical humidity | Yes |
| Medium | Humidity w/ occasional rain | Yes |
| Medium | Nearby steam/spray | Yes |
| Medium | Other mild water contact | Yes |
| High | Occasional washdowns | Yes |
| High | Severe water contact | Yes |
| High | Submerged | Yes |

### 🔹 ESI Matrix
| CI Factor | WCCI Factor | Breather Type |
|-----------|-------------|---------------|
| Low + Very Low/Low/Medium | – | Básico |
| Low + High | Extended service |
| Medium + Low | Básico |
| Medium + Medium/High | Extended service |
| High + cualquiera | Extended service |

---

## 📝 Reglas de selección

1. **Definir si requiere breather**  
   - Solo si Criticality = A o B.  
2. **Calcular CFM requerido**  
   - Con ΔT + volúmenes.  
3. **Descartar modelos fuera de rango CFM**.  
4. **Ajustar por condiciones operativas**  
   - 4.1 Agua (WCCI Very Low / Low / Medium / High).  
   - 4.2 Si no se requiere desecante (Very Low).  
   - 4.3 Humedad relativa:  
     - <75% → normal  
     - ≥75% → Extended service  
   - 4.4 Contaminación (CI).  
   - 4.5 Entorno limpio (CI=Low) → no forzar filtro partículas.  
   - 4.6 Extended service index (rebuildable/disposable).  
   - 4.7 Oil mist → requiere control de niebla.  
   - 4.8 Vibración:  
     - <0.2 ips → normal  
     - 0.2–0.4 ips → heavy-duty  
     - >0.4 ips → heavy-duty obligatorio  
   - 4.9 Aplicaciones móviles → heavy-duty.  
5. **Ajustar por capacidad de retención de agua**  
   - Volumen de sump grande → mayor capacidad (usar Sump Volume MAX del catálogo).  
6. **Ajustar por espacio disponible**  
   - Validar altura y diámetro con puerto.  
7. **Recomendación final**  
   - 7.1 Óptimo: cabe y cumple.  
   - 7.2 Óptimo modificado: no cabe → recomendar instalación remota.  
   - 7.3 Sub-óptimo: cabe, pero no cumple todo (ej. sin heavy-duty).  

---

# ✅ Flujo simplificado

1. Requiere breather (Criticidad).  
2. Calcular CFM.  
3. Filtrar catálogo por CFM.  
4. Ajustar por ambiente (agua, RH, CI, oil mist, vibración, móvil).  
5. Ajustar por retención de agua (Sump MAX).  
6. Validar espacio.  
7. Recomendar: Óptimo / Modificado / Sub-óptimo.  
