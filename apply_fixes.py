#!/usr/bin/env python3
"""Apply UI/UX fixes to dental_clinic.py"""
import re

with open('dental_clinic.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Add date picker button to patient form (first occurrence only - Add Patient modal)
old_pattern = r'(<label data-i18n="date_of_birth">Date of Birth</label>\s*)<input type="text" name="date_of_birth" placeholder="DD/MM/YYYY" title="Enter date in DD/MM/YYYY format">'
new_text = r'\1<div style="display:flex;gap:8px;align-items:flex-end;"><input type="text" name="date_of_birth" placeholder="DD/MM/YYYY" style="flex:1;"><button type="button" class="btn btn-warning" onclick="showDatePickerForPatient()" style="padding:11px 14px;min-width:48px;">📅</button></div>'

content_before = content
content = re.sub(old_pattern, new_text, content, count=1)
if content != content_before:
    print("✅ Fix 1: Added date picker button to patient form")
else:
    print("⚠️ Fix 1: Pattern not found")

# Fix 2: Add date picker modal CSS
css_insert = '''
        /* Date picker modal */
        .date-picker-modal { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.4); z-index: 10000; align-items: center; justify-content: center; }
        .date-picker-modal.active { display: flex; }
        .date-picker-modal-content { background: #fff; border-radius: 16px; padding: 20px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); max-width: 320px; width: 90%; }
        body[data-theme="dark"] .date-picker-modal-content { background: #0e1727; color: #f1f5f9; }
        .date-picker-modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .date-picker-modal-header button { background: none; border: none; font-size: 24px; cursor: pointer; color: #627386; }
        .date-picker-modal-month { font-weight: 700; font-size: 1.1rem; text-align: center; }
        .date-picker-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; margin-top: 14px; }
        .date-picker-day { text-align: center; padding: 6px; border-radius: 8px; cursor: pointer; font-size: 0.9rem; border: 1px solid transparent; }
        .date-picker-day:hover { background: #e8f1fa; }
        .date-picker-day-name { font-weight: 700; font-size: 0.75rem; color: #627386; padding: 8px 0; }
        body[data-theme="dark"] .date-picker-day:hover { background: rgba(255,255,255,0.08); }
        .date-picker-day.empty { cursor: default; }
        .date-picker-day.today { background: #e6f7f5; border-color: #13b5a7; color: #0f6d7b; font-weight: 700; }
'''

css_marker = '.calendar-empty { font-size: 11px; color: #8ba0b5; margin-top: 6px; }'
if css_marker in content and css_insert.strip() not in content:
    content = content.replace(css_marker, css_marker + css_insert)
    print("✅ Fix 2: Added date picker CSS")
else:
    print("⚠️ Fix 2: CSS marker not found or already added")

# Fix 3: Add date picker JavaScript functions
js_functions = '''
        function showDatePickerForPatient() {
            showCalendarPickerModal((selectedDate) => {
                const dateInput = document.querySelector('#add-patient-form input[name="date_of_birth"]');
                if (dateInput && selectedDate) {
                    dateInput.value = selectedDate;
                }
            });
        }

        function showCalendarPickerModal(onDateSelect) {
            if (!document.getElementById('date-picker-modal')) {
                const modal = document.createElement('div');
                modal.id = 'date-picker-modal';
                modal.className = 'date-picker-modal';
                modal.innerHTML = `
                    <div class="date-picker-modal-content">
                        <div class="date-picker-modal-header">
                            <button type="button" onclick="changePickerMonth(-1)">❮</button>
                            <div class="date-picker-modal-month" id="picker-month-label"></div>
                            <button type="button" onclick="changePickerMonth(1)">❯</button>
                        </div>
                        <div id="picker-calendar-grid" class="date-picker-grid"></div>
                        <div style="display: flex; gap: 8px; margin-top: 16px;">
                            <button class="btn btn-warning" type="button" onclick="closePickerModal()">Cancel</button>
                            <button class="btn btn-primary" type="button" onclick="selectTodayInPicker()">Today</button>
                        </div>
                    </div>
                </div>
                `;
                document.body.appendChild(modal);
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) closePickerModal();
                });
            }
            window.datePickerCallback = onDateSelect;
            window.pickerDate = new Date();
            renderPickerCalendar();
            document.getElementById('date-picker-modal').classList.add('active');
        }

        function renderPickerCalendar() {
            const year = window.pickerDate.getFullYear();
            const month = window.pickerDate.getMonth();
            const firstDay = new Date(year, month, 1);
            const startDay = firstDay.getDay();
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            const monthLabelEl = document.getElementById('picker-month-label');
            const today = new Date();
            const locale = currentLanguage === 'ar' ? 'ar-EG' : 'en-US';
            const monthStr = window.pickerDate.toLocaleDateString(locale, { month: 'long', year: 'numeric' });
            monthLabelEl.textContent = monthStr;
            const dayNames = currentLanguage === 'ar'
                ? ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
                : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            const gridEl = document.getElementById('picker-calendar-grid');
            gridEl.innerHTML = dayNames.map(d => `<div class="date-picker-day-name">${d}</div>`).join('') +
                Array.from({length: startDay}, () => '<div class="date-picker-day empty"></div>').join('') +
                Array.from({length: daysInMonth}, (_, i) => {
                    const day = i + 1;
                    const dateStr = `${String(day).padStart(2, '0')}/${String(month + 1).padStart(2, '0')}/${year}`;
                    const isToday = today.getFullYear() === year && today.getMonth() === month && today.getDate() === day;
                    const todayClass = isToday ? 'today' : '';
                    return `<div class="date-picker-day ${todayClass}" onclick="selectPickerDate('${dateStr}')">${day}</div>`;
                }).join('');
        }

        function changePickerMonth(offset) {
            if (!window.pickerDate) window.pickerDate = new Date();
            window.pickerDate = new Date(window.pickerDate.getFullYear(), window.pickerDate.getMonth() + offset, 1);
            renderPickerCalendar();
        }

        function selectPickerDate(dateStr) {
            if (window.datePickerCallback) {
                window.datePickerCallback(dateStr);
            }
            closePickerModal();
        }

        function selectTodayInPicker() {
            const today = new Date();
            const day = String(today.getDate()).padStart(2, '0');
            const month = String(today.getMonth() + 1).padStart(2, '0');
            const year = today.getFullYear();
            selectPickerDate(`${day}/${month}/${year}`);
        }

        function closePickerModal() {
            const modal = document.getElementById('date-picker-modal');
            if (modal) modal.classList.remove('active');
        }
'''

js_marker = 'function showAddPatientModal() {'
if js_marker in content and 'showCalendarPickerModal' not in content:
    # Insert before showAddPatientModal
    content = content.replace(js_marker, js_functions + '\n        ' + js_marker)
    print("✅ Fix 3: Added date picker JavaScript functions")
else:
    print("⚠️ Fix 3: JS insertion marker not found or already added")

# Write the updated content back
with open('dental_clinic.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✅ All fixes applied successfully!")
