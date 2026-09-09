import { createContext, useContext, useState, type ReactNode } from 'react'

export type Lang = 'en' | 'ru'

const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (en: string, ru: string) => string }>({
  lang: 'en',
  setLang: () => undefined,
  t: (en) => en,
})

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => (localStorage.getItem('dash-lang') as Lang) || 'en')
  const setLang = (l: Lang) => {
    setLangState(l)
    localStorage.setItem('dash-lang', l)
    document.documentElement.lang = l
  }
  const t = (en: string, ru: string) => (lang === 'ru' ? ru : en)
  return <LangContext.Provider value={{ lang, setLang, t }}>{children}</LangContext.Provider>
}

export const useLang = () => useContext(LangContext)

export function LangToggle() {
  const { lang, setLang } = useLang()
  return (
    <button
      className="button tiny subtle lang-toggle"
      title="Language / Язык"
      onClick={() => setLang(lang === 'en' ? 'ru' : 'en')}
    >
      {lang === 'en' ? 'RU' : 'EN'}
    </button>
  )
}
