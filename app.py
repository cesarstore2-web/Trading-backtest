                for wk in range(1, 5):
                    if wk in w_stats:
                        agg_weekly[wk]["wins"] += w_stats[wk]["wins"]
                        agg_weekly[wk]["losses"] += w_stats[wk]["losses"]
                        agg_weekly[wk]["open"] += w_stats[wk]["open"]
                        agg_weekly[wk]["profit"] += w_stats[wk]["profit"]
        except Exception as e:
            st.warning(f"تعذر جلب بيانات {name}: {e}")

# استخراج بيانات الأسبوع الحالي (الأسبوع 4 هو الأحدث في الكود)
curr_wk = agg_weekly[4]
cw_wins = curr_wk["wins"]
cw_losses = curr_wk["losses"]
cw_open = curr_wk["open"]
cw_profit = curr_wk["profit"]
cw_closed = cw_wins + cw_losses
cw_winrate = (cw_wins / cw_closed * 100) if cw_closed > 0 else 0.0

# --- عرض ملخص الأسبوع الحالي ---
st.subheader("🔥 ملخص الأداء للأسبوع الحالي (آخر 7 أيام)")
c1, c2, c3, c4 = st.columns(4)
c1.metric("ناجحة", cw_wins)
c2.metric("خاسرة", cw_losses)
c3.metric("مفتوحة", cw_open)
c4.metric("الربح الصافي", f"{cw_profit:.2f}$", delta=f"{cw_profit:.2f}$")

st.info(f"**نسبة النجاح للأسبوع الحالي:** {cw_winrate:.1f}% | **إجمالي الصفقات المغلقة:** {cw_closed} صفقة")

# --- تفاصيل العملات للأسبوع الحالي ---
if details:
    st.markdown("**📋 تفاصيل الصفقات حسب العملة (الأسبوع الحالي):**")
    df_details = pd.DataFrame(details).sort_values(by="الربح الصافي ($)", ascending=False)
    st.dataframe(df_details, use_container_width=True, hide_index=True)
else:
    st.warning("لا توجد صفقات مسجلة في الأسبوع الحالي وفق الإعدادات المختارة.")

# --- مقارنة سريعة مع الأسابيع السابقة ---
with st.expander("📅 عرض سجل الأسابيع الأربعة (للمقارنة)"):
    weekly_rows = []
    for wk in range(4, 0, -1): # ترتيب من الأحدث للأقدم
        w_data = agg_weekly[wk]
        label = "الأسبوع الحالي" if wk == 4 else f"قبل {4 - wk} أسابيع"
        weekly_rows.append({
            "الفترة": label,
            "ناجحة": w_data["wins"],
            "خاسرة": w_data["losses"],
            "مفتوحة": w_data["open"],
            "الربح الصافي ($)": round(w_data["profit"], 2)
        })
    st.dataframe(pd.DataFrame(weekly_rows), use_container_width=True, hide_index=True)
