# --- عرض النتائج مع أزرار الإظهار والإخفاء ---
st.subheader("📊 ملخص الأداء (آخر 7 أيام)")
m1, m2, m3, m4 = st.columns(4)
m1.metric("الربح الصافي ($)", f"{tot_p:.2f}$")
m2.metric("صفقات ناجحة ✅", tot_w)
m3.metric("صفقات خاسرة ❌", tot_l)
m4.metric("صفقات مفتوحة ⏳", tot_o)

st.divider()

# 1. مربع إظهار أو إخفاء تفاصيل الصفقات
show_details = st.checkbox("إظهار تفاصيل الصفقات حسب العملة (7 أيام)", value=False)
if show_details:
    if details:
        df_details = pd.DataFrame(details).sort_values(by="الربح الصافي ($)", ascending=False)
        st.dataframe(df_details, use_container_width=True, hide_index=True)
    else:
        st.info("لم يتم رصد أي صفقات مطابقة للشروط خلال آخر 7 أيام.")

# 2. مربع إظهار أو إخفاء جدول أداء الأسابيع
show_weekly = st.checkbox("إظهار جدول أداء الاستراتيجية (آخر 4 أسابيع)", value=False)
if show_weekly:
    weekly_rows = []
    for wk in range(1, 5):
        label = f"الأسبوع {wk}" + (" (الأحدث)" if wk == 4 else "")
        weekly_rows.append({
            "الفترة": label,
            "ناجحة": agg_weekly[wk]["wins"],
            "خاسرة": agg_weekly[wk]["losses"],
            "مفتوحة": agg_weekly[wk]["open"],
            "الربح الصافي ($)": round(agg_weekly[wk]["profit"], 2)
        })
    st.dataframe(pd.DataFrame(weekly_rows), use_container_width=True, hide_index=True)
