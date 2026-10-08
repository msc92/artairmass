// Reflection helpers: JSkyCalc's classes live in the default package with package-private members.
function cls(n){ return java.lang.Class.forName(n); }
function make(n, types, args){ var c=cls(n).getDeclaredConstructor(Java.to(types,"java.lang.Class[]")); c.setAccessible(true); return c.newInstance(Java.to(args,"java.lang.Object[]")); }
function get(o,f){ var fl=o.getClass().getDeclaredField(f); fl.setAccessible(true); return fl.get(o); }
function call(o,m){ var mm=o.getClass().getDeclaredMethod(m); mm.setAccessible(true); return mm.invoke(o); }
var S=java.lang.String.class, SA=Java.type("java.lang.String[]").class, D=java.lang.Double.TYPE;
var site=make("Site",[SA],[Java.to(["Las Campanas","4.7133","-29.0083","4.","-1","Chilean","C","2282.","2282."],"java.lang.String[]")]);
var ww=make("WhenWhere",[D,cls("Site")],[2461000.5,site]);
var cel=make("Celest",[S,S,S],["13 29 52.7","47 11 43","2000"]);
var ob=make("Observation",[cls("WhenWhere"),cls("Celest")],[ww,cel]);
call(ob,"ComputeSunMoon");
print("LST",get(ww,"sidereal")," alt",get(ob,"altitude")," az",get(ob,"azimuth")," airmass",get(ob,"airmass")," moonobj",get(ob,"moonobj"));
