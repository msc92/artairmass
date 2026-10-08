// Runs JSkyCalc's own classes headless (Java 8 Nashorn `jjs`) over the cases in
// validation/fixtures/cases.json and writes validation/fixtures/jskycalc_reference.json.
// JSkyCalc's classes are package-private, so everything goes through reflection.
//
//   jjs -cp JSkyCalc-master/JSkyCalc.jar validation/harness/jskycalc_oracle.js -- <cases.json> <out.json>

var Files = java.nio.file.Files, Paths = java.nio.file.Paths;
var D = java.lang.Double.TYPE, I = java.lang.Integer.TYPE;
var S = java.lang.String.class, SA = Java.type("java.lang.String[]").class;
function cls(n) { return java.lang.Class.forName(n); }
function make(n, types, args) {
    var c = cls(n).getDeclaredConstructor(Java.to(types, "java.lang.Class[]"));
    c.setAccessible(true);
    return c.newInstance(Java.to(args, "java.lang.Object[]"));
}
function get(o, f) { var fl = o.getClass().getDeclaredField(f); fl.setAccessible(true); return fl.get(o); }
function call(o, m, types, args) {
    var mm = o.getClass().getDeclaredMethod(m, Java.to(types || [], "java.lang.Class[]"));
    mm.setAccessible(true);
    return mm.invoke(o, Java.to(args || [], "java.lang.Object[]"));
}
function scall(c, m, types, args) {
    var mm = cls(c).getDeclaredMethod(m, Java.to(types, "java.lang.Class[]"));
    mm.setAccessible(true);
    return mm.invoke(null, Java.to(args, "java.lang.Object[]"));
}
function jdOf(ww) { return get(get(ww, "when"), "jd"); }
function hrs(c) { return get(get(c, "Alpha"), "value"); }
function deg(c) { return get(get(c, "Delta"), "value"); }

var args = arguments;
var cases = JSON.parse(new java.lang.String(Files.readAllBytes(Paths.get(args[0])), "UTF-8"));
var out = [];
for (var i = 0; i < cases.length; i++) {
    var cs = cases[i];
    var site = make("Site", [SA], [Java.to(cs.jsk_site, "java.lang.String[]")]);
    var ww = make("WhenWhere", [D, cls("Site")], [cs.jd, site]);
    call(ww, "ComputeSunMoon");
    var res = {id: cs.id, jd: cs.jd, sidereal: get(ww, "sidereal"),
        sun_alt: get(ww, "altsun"), sun_az: get(ww, "azsun"), ztwilight: get(ww, "twilight"),
        moon_alt: get(ww, "altmoon"), moon_az: get(ww, "azmoon"), sunmoon: get(ww, "sunmoon"),
        moon_illum: get(ww, "moonillum"),
        moon_ra: hrs(get(get(ww, "moon"), "topopos")), moon_dec: deg(get(get(ww, "moon"), "topopos")),
        moon_dist: get(get(get(ww, "moon"), "topopos"), "distance"),
        sun_ra: hrs(get(get(ww, "sun"), "topopos")), sun_dec: deg(get(get(ww, "sun"), "topopos")),
        phase_descr: scall("Moon", "MoonPhaseDescr", [D], [cs.jd]), targets: []};
    var alm = make("NightlyAlmanac", [cls("WhenWhere")], [ww]);
    res.almanac = {};
    var names = ["sunset", "sunrise", "eveningTwilight", "morningTwilight", "nightcenter", "moonrise", "moonset"];
    for (var k = 0; k < names.length; k++) res.almanac[names[k]] = jdOf(get(alm, names[k]));
    var planets = make("Planets", [cls("WhenWhere")], [ww]);
    for (var j = 0; j < cs.targets.length; j++) {
        var tg = cs.targets[j];
        var cel = make("Celest", [S, S, S], [tg.ra, tg.dec, tg.equinox]);
        var ob = make("Observation", [cls("WhenWhere"), cls("Celest")], [ww, cel]);
        call(ob, "ComputeSunMoon");
        call(ob, "computebary", [cls("Planets")], [planets]);
        call(ob, "computepifacs");
        var c2000 = get(ob, "c2000");
        call(c2000, "galactic");
        var pif = get(ob, "pifacs");
        var t = {name: tg.name, ha: get(get(ob, "ha"), "value"), alt: get(ob, "altitude"),
            az: get(ob, "azimuth"), airmass: get(ob, "airmass"), parallactic: get(ob, "parallactic"),
            moonobj: get(ob, "moonobj"), sunobj: get(ob, "sunobj"), moonlight: get(ob, "moonlight"),
            barytcor: get(ob, "barytcor"), baryvcor: get(ob, "baryvcor"), baryjd: get(ob, "baryjd"),
            ra_date: hrs(get(ob, "current")), dec_date: deg(get(ob, "current")),
            ra_2000: hrs(c2000), dec_2000: deg(c2000),
            gal_l: get(c2000, "galong"), gal_b: get(c2000, "galat"),
            pifac_e: pif[0], pifac_n: pif[1],
            constel: scall("Constel", "getconstel", [cls("Celest")], [get(ob, "current")])};
        if (tg.seasonal) {
            // Seasonal only recomputes when the date moved > 5 d since its last run,
            // so prime it 10 days away and then update to the real instant.
            var wwFar = make("WhenWhere", [D, cls("Site")], [cs.jd + 10.0, site]);
            var obFar = make("Observation", [cls("WhenWhere"), cls("Celest")], [wwFar, cel]);
            var season = make("Seasonal", [cls("Observation")], [obFar]);
            call(season, "Update", [cls("Observation")], [ob]);
            var td = get(season, "tabledata");
            var rows = [];
            for (var r = 0; r < td.length; r++) {
                var row = [];
                for (var cc = 0; cc < td[r].length; cc++) row.push(String(td[r][cc]).trim());
                rows.push(row);
            }
            t.seasonal = rows;
            t.seasonal_jdnew = Java.from(get(season, "jdnew"));
            t.seasonal_jdfull = Java.from(get(season, "jdfull"));
        }
        res.targets.push(t);
    }
    out.push(res);
}
Files.write(Paths.get(args[1]), JSON.stringify(out, null, 1).getBytes("UTF-8"));
print("wrote " + out.length + " cases to " + args[1]);
