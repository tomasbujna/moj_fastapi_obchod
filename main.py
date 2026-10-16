import os
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import models
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

current_dir = os.path.dirname(os.path.realpath(__file__))
templates_dir = os.path.join(current_dir, "templates")
templates = Jinja2Templates(directory=templates_dir)

ADMIN_HESLO = "e*K@95Oo"

# Dočasný košík zostáva v pamäti (pri reálnom e-shope sa ukladá do session/databázy)
kosik = []
kupon_kod = ""


def vypocitaj_zlavu(cena: float, kupon: str) -> float:
    kupon_clean = kupon.strip().upper()
    if kupon_clean == "ZLAVA10":
        return cena * 0.9
    if kupon_clean == "ZLAVA20":
        return cena * 0.8
    return cena


def nacitaj_sklad_dict(db: Session):
    polozky = db.query(models.Tovar).all()
    return {p.nazov: {"cena": p.cena, "pocet": p.pocet} for p in polozky}


@app.get("/", response_class=HTMLResponse)
def domov(request: Request, db: Session = Depends(get_db)):
    sklad_dict = nacitaj_sklad_dict(db)
    
    kosik_spocitany = {}
    for polozka in kosik:
        kosik_spocitany[polozka] = kosik_spocitany.get(polozka, 0) + 1

    celkova_suma = sum(sklad_dict[nazov]["cena"] for nazov in kosik if nazov in sklad_dict)
    spolu_k_uhrade = vypocitaj_zlavu(celkova_suma, kupon_kod)
    
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={
            "sklad": sklad_dict,
            "kosik": kosik,
            "kosik_spocitany": kosik_spocitany,
            "suma_pred_zlavou": round(celkova_suma, 2),
            "spolu_k_uhrade": round(spolu_k_uhrade, 2),
            "kupon": kupon_kod
        }
    )


@app.post("/pridat", response_class=HTMLResponse)
def pridat_do_kosika(request: Request, tovar: str = Form(...), db: Session = Depends(get_db)):
    tovar_db = db.query(models.Tovar).filter(models.Tovar.nazov == tovar).first()
    if tovar_db and tovar_db.pocet > 0:
        kosik.append(tovar)
        tovar_db.pocet -= 1
        db.commit()
    return domov(request, db)


@app.post("/odobrat-jeden", response_class=HTMLResponse)
def odobrat_jeden(request: Request, tovar: str = Form(...), db: Session = Depends(get_db)):
    if tovar in kosik:
        kosik.remove(tovar)
        tovar_db = db.query(models.Tovar).filter(models.Tovar.nazov == tovar).first()
        if tovar_db:
            tovar_db.pocet += 1
            db.commit()
    return domov(request, db)


@app.post("/odobrat-vsetky", response_class=HTMLResponse)
def odobrat_vsetky(request: Request, tovar: str = Form(...), db: Session = Depends(get_db)):
    global kosik
    pocet_v_kosiku = kosik.count(tovar)
    if pocet_v_kosiku > 0:
        kosik = [item for item in kosik if item != tovar]
        tovar_db = db.query(models.Tovar).filter(models.Tovar.nazov == tovar).first()
        if tovar_db:
            tovar_db.pocet += pocet_v_kosiku
            db.commit()
    return domov(request, db)


@app.post("/zlavovy-kupon", response_class=HTMLResponse)
def aplikuj_kupon(request: Request, kupon: str = Form(""), db: Session = Depends(get_db)):
    global kupon_kod
    kupon_kod = kupon
    return domov(request, db)


@app.post("/dokoncit-nakup", response_class=HTMLResponse)
def dokoncit_nakup(request: Request, db: Session = Depends(get_db)):
    global kosik, kupon_kod
    kosik.clear()
    kupon_kod = ""
    return domov(request, db)


@app.post("/reset", response_class=HTMLResponse)
def reset_kosik(request: Request, db: Session = Depends(get_db)):
    global kosik, kupon_kod
    for nazov in kosik:
        tovar_db = db.query(models.Tovar).filter(models.Tovar.nazov == nazov).first()
        if tovar_db:
            tovar_db.pocet += 1
    db.commit()
    kosik.clear()
    kupon_kod = ""
    return domov(request, db)


# --- ADMIN PANEL ---
@app.get("/admin", response_class=HTMLResponse)
def admin_panel_get(request: Request, db: Session = Depends(get_db)):
    sklad_dict = nacitaj_sklad_dict(db)
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"sklad": sklad_dict, "prihlaseny": False, "chyba": None, "heslo": ""}
    )


@app.post("/admin", response_class=HTMLResponse)
def admin_panel_post(request: Request, heslo: str = Form(""), db: Session = Depends(get_db)):
    sklad_dict = nacitaj_sklad_dict(db)
    if heslo == ADMIN_HESLO:
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={"sklad": sklad_dict, "prihlaseny": True, "heslo": heslo, "chyba": None}
        )
    else:
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={"sklad": sklad_dict, "prihlaseny": False, "chyba": "Nesprávne heslo!", "heslo": ""}
        )


@app.post("/admin/pridat-tovar", response_class=HTMLResponse)
def pridat_tovar_sklad(
    request: Request, 
    nazov: str = Form(...), 
    cena: float = Form(...), 
    pocet: int = Form(...),
    heslo: str = Form(...),
    db: Session = Depends(get_db)
):
    if heslo != ADMIN_HESLO:
        sklad_dict = nacitaj_sklad_dict(db)
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={"sklad": sklad_dict, "prihlaseny": False, "chyba": "Neoprávnený prístup!", "heslo": ""}
        )

    nazov_clean = nazov.strip().lower()
    tovar_db = db.query(models.Tovar).filter(models.Tovar.nazov == nazov_clean).first()
    
    if tovar_db:
        tovar_db.pocet += pocet
        tovar_db.cena = cena
    else:
        novy_tovar = models.Tovar(nazov=nazov_clean, cena=cena, pocet=pocet)
        db.add(novy_tovar)
        
    db.commit()
    sklad_dict = nacitaj_sklad_dict(db)
        
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"sklad": sklad_dict, "prihlaseny": True, "heslo": heslo, "chyba": None}
    )


@app.post("/admin/zmazat-tovar", response_class=HTMLResponse)
def zmazat_tovar_sklad(
    request: Request,
    nazov: str = Form(...),
    heslo: str = Form(...),
    db: Session = Depends(get_db)
):
    if heslo != ADMIN_HESLO:
        sklad_dict = nacitaj_sklad_dict(db)
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={"sklad": sklad_dict, "prihlaseny": False, "chyba": "Neoprávnený prístup!", "heslo": ""}
        )

    nazov_clean = nazov.strip().lower()
    tovar_db = db.query(models.Tovar).filter(models.Tovar.nazov == nazov_clean).first()
    
    if tovar_db:
        db.delete(tovar_db)
        db.commit()
        global kosik
        kosik = [item for item in kosik if item != nazov_clean]

    sklad_dict = nacitaj_sklad_dict(db)

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"sklad": sklad_dict, "prihlaseny": True, "heslo": heslo, "chyba": None}
    )