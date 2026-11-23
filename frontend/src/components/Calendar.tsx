import React, { useState } from 'react';
import { useSintomasStore } from '../store/useSintomasStore';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export const Calendar: React.FC<{ onDayClick?: (day: number) => void }> = ({ onDayClick }) => {
  const { selectedDate, setSelectedDate, calendarioInfo, fetchCalendarioInfo } = useSintomasStore();
  
  // Estado para controlar qual mês estamos visualizando
  const [viewDate, setViewDate] = useState(new Date(selectedDate));

  // Sincronizar visualização quando a data selecionada mudar externamente
  React.useEffect(() => {
    setViewDate(new Date(selectedDate));
  }, [selectedDate]);

  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();

  const getDaysInMonth = (y: number, m: number) => new Date(y, m + 1, 0).getDate();
  const getFirstDayOfMonth = (y: number, m: number) => new Date(y, m, 1).getDay();

  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  const daysInPrevMonth = getDaysInMonth(year, month - 1);

  const prevMonthDays = Array.from({ length: firstDay }, (_, i) => daysInPrevMonth - firstDay + i + 1);
  const currentMonthDays = Array.from({ length: daysInMonth }, (_, i) => i + 1);
  const nextMonthDaysLength = 42 - (prevMonthDays.length + currentMonthDays.length);
  const nextMonthDays = Array.from({ length: nextMonthDaysLength }, (_, i) => i + 1);

  const monthNames = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

  const handlePrevMonth = () => setViewDate(new Date(year, month - 1, 1));
  const handleNextMonth = () => setViewDate(new Date(year, month + 1, 1));

  // Carrega informações de sintomas para o mês visualizado
  React.useEffect(() => {
    fetchCalendarioInfo(year, month + 1);
  }, [year, month, fetchCalendarioInfo]);

  const handleDayClick = (day: number) => {
    const newDate = new Date(year, month, day);
    setSelectedDate(newDate);
    if (onDayClick) onDayClick(day);
  };

  const hasSintomaOnDay = (day: number) => {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    return !!calendarioInfo[dateStr];
  };

  const sintomaCountOnDay = (day: number) => {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    return calendarioInfo[dateStr] || 0;
  };

  // Layout fluido: o calendário ocupa a altura que o pai der (flex-1). A grade tem
  // 6 linhas iguais e cada célula é um "container" (CSS container queries): o botão
  // do dia é um quadrado do tamanho que couber na célula, no máximo 48 px.
  const celula = "[container-type:size] min-h-0 flex items-center justify-center";
  const tamanhoDia = "size-[min(100cqw,100cqh,3rem)] text-[clamp(0.8rem,42cqh,1.25rem)]";

  return (
    <div className="w-full h-full min-h-0 flex flex-col py-[clamp(0.25rem,1.5dvh,1rem)]">
      <div className="flex items-center justify-between mb-[clamp(0.5rem,3dvh,2rem)] px-2 shrink-0">
        <button onClick={handlePrevMonth} aria-label="Mês anterior" className="size-[clamp(2.25rem,6dvh,3rem)] bg-white rounded-full flex items-center justify-center text-brand-navy shadow-sm active:scale-95 transition-transform">
          <ChevronLeft size={24} />
        </button>
        <h2 className="text-brand-navy font-bold text-[clamp(1.05rem,2.6dvh,1.25rem)]">{monthNames[month]} {year}</h2>
        <button onClick={handleNextMonth} aria-label="Próximo mês" className="size-[clamp(2.25rem,6dvh,3rem)] bg-white rounded-full flex items-center justify-center text-brand-navy shadow-sm active:scale-95 transition-transform">
          <ChevronRight size={24} />
        </button>
      </div>

      {/* Cabeçalho dos dias da semana */}
      <div className="grid grid-cols-7 text-center mb-[clamp(0.25rem,1.5dvh,1rem)] shrink-0">
        {['D', 'S', 'T', 'Q', 'Q', 'S', 'S'].map((day, i) => (
           <div key={`weekday-${i}`} className="text-brand-navy/60 text-sm font-bold">{day}</div>
        ))}
      </div>

      <div className="grid grid-cols-7 grid-rows-6 flex-1 min-h-0 text-center">
        {prevMonthDays.map((day, i) => (
          <div key={`prev-${i}`} className={celula}>
            <span className={`${tamanhoDia} flex items-center justify-center text-brand-navy/30 font-medium`}>{day}</span>
          </div>
        ))}

        {currentMonthDays.map(day => {
          const isSelected = selectedDate.getDate() === day &&
                             selectedDate.getMonth() === month &&
                             selectedDate.getFullYear() === year;

          const hasSintoma = hasSintomaOnDay(day);
          const sintomaCount = sintomaCountOnDay(day);

          return (
            <div key={day} className={celula}>
              <button
                onClick={() => handleDayClick(day)}
                className={`${tamanhoDia} flex flex-col items-center justify-center font-medium transition-all relative rounded-2xl
                  ${isSelected
                    ? 'bg-brand-active text-white ring-2 ring-brand-active ring-offset-2 ring-offset-brand-blue'
                    : hasSintoma
                      ? 'bg-brand-blue/25 ring-1 ring-brand-blue/40 text-brand-navy font-bold hover:bg-brand-blue/30'
                      : 'text-brand-navy hover:bg-black/5'
                  }
                `}
              >
                <span>{day}</span>
                {hasSintoma && (
                  sintomaCount > 1 ? (
                    <span
                      className={`absolute -bottom-1 min-w-[18px] h-[18px] px-1 rounded-full flex items-center justify-center text-[9px] font-black leading-none
                        ${isSelected ? 'bg-white text-brand-active' : 'bg-brand-blue-dark text-white'}
                      `}
                    >
                      {sintomaCount}
                    </span>
                  ) : (
                    <span className={`w-2.5 h-2.5 rounded-full absolute -bottom-1 ring-2 ring-white ${isSelected ? 'bg-white' : 'bg-brand-blue-dark'}`} />
                  )
                )}
              </button>
            </div>
          );
        })}

        {nextMonthDays.map((day, i) => (
          <div key={`next-${i}`} className={celula}>
            <span className={`${tamanhoDia} flex items-center justify-center text-brand-navy/30 font-medium`}>{day}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
