
### CONFIG.PY  
**SITE_KEY** - _SITEKEY для решения капчи Twitter при разморозке аккаунта, не менять_  
**SITE_URL** - _SITEURL Twitter для разморозки аккаунта, не менять_  
**FIRSTCAPTCHA_API_KEY** - _API KEY с https://1stcaptcha.com/ (не забудьте пополнить баланс)_  
**CHANGE_PROXY_URL** - _Ссылка для смены IP при использовании мобильных прокси со сменой по ссылке_  
**REPEATS_ATTEMPTS** - _Количество попыток для повторения выполнения скрипта в случае ошибки_
**ACCOUNT_TOO_NEW_ATTEMPTS** - _Количество попыток повторного выполнения авторизации MEME при ошибке Account Too New_  
**ACCOUNT_UNAUTHORIZED_ATTEMPTS** - _Количество попыток повторного выполнения авторизации MEME при ошибке Unauthorized_  
**SLEEP_BETWEEN_TASKS** - _Время сна между выполнением заданий MEME (число, ex: 1, 5, 10 // диапазон, ex: 1-5, 5-7, 2-6)_  
**SLEEP_AFTER_PROXY_CHANGING** - _Время сна после смены Proxy_  

### twitter_tokens.txt  
_Заполняем **auth_token**'s от аккаунтов, каждый с новой строки_  

### proxies.txt  
_Список прокси (вставляете либо одну мобильную и указываете CHANGE_PROXY_URL в конфиге, либо вставляете список
обычных проксей). Формат `http://user:pass@ip:port`

### log files  
_**empty_attemps.txt** - файл с токенами аккаунтов, попытки для повтора которых закончились (см config.py -> REPATS_COUNT)_  
_**registered.txt** - файл успешно зарегистрированных аккаунтов_  
_**suspended_accounts.txt** - файл токенов аккаунтов, заблокированных в Twitter_  
_**account_too_new.txt** - Файл токенов аккаунтов, не подходящих по параметрам_
