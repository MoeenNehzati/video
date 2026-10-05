import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.prefs.Preferences;
import org.jjazz.rhythmdatabase.api.*;
import org.jjazz.rhythmdatabase.spi.SharedRdbInstanceProvider;
import org.jjazz.rhythm.spi.RhythmDirsLocator;
import org.openide.util.lookup.ServiceProvider;
import org.jjazz.importers.api.MusicXMLFileReader;
import org.jjazz.chordleadsheet.api.item.CLI_ChordSymbol;
import org.jjazz.chordleadsheet.spi.item.CLI_Factory;
import org.jjazz.phrase.api.Phrase;
import org.jjazz.phrase.api.NoteEvent;
import org.jjazz.midimix.spi.MidiMixManager;
import org.jjazz.outputsynth.spi.OutputSynthManager;
import org.jjazz.rhythmmusicgeneration.api.SongSequenceBuilder;
import org.jjazz.rhythmparametersimpl.api.RP_SYS_Variation;
import org.jjazz.song.spi.SongContextFactory;
import org.jjazz.midi.api.synths.GMSynth;
import javax.sound.midi.MidiSystem;
import org.jjazz.rhythmparametersimpl.api.RP_SYS_Intensity;
import org.jjazz.rhythmparametersimpl.api.RP_SYS_Fill;

public class ChildExperiment {
  @ServiceProvider(service=SharedRdbInstanceProvider.class)
  public static class Database implements SharedRdbInstanceProvider {
    private DefaultRhythmDatabaseImpl db;
    public Future<?> initialize() {
      db=new DefaultRhythmDatabaseImpl(Preferences.userRoot().node("music-video-arrangement"));
      db.addRhythmsFromRhythmProviders(false,false,false);
      return CompletableFuture.completedFuture(null);
    }
    public boolean isInitialized(){return db!=null;}
    public RhythmDatabase get(){if(db==null)initialize();return db;}
    public void markForStartupRefresh(boolean b){}
    public boolean isMarkedForStartupRefresh(){return false;}
  }
  public static void main(String[] args) throws Exception {
    try {
      System.setProperty("java.util.logging.SimpleFormatter.format","%4$s %3$s %5$s%n");
      Locale.setDefault(Locale.ENGLISH);
      File rhythms=new File(args[0]);if(!rhythms.isDirectory())throw new IOException("Missing rhythms directory");
      RhythmDirsLocator.getDefault().setUserRhythmsDirectory(rhythms);
      var db=RhythmDatabase.getSharedInstance();
      for(int i=1;i<args.length;i++)generate(db,Path.of(args[i]));
    } catch(Throwable t){t.printStackTrace();System.exit(1);}
    System.exit(0);
  }

  static void generate(RhythmDatabase db,Path dir)throws Exception {
    Properties p=new Properties();try(var reader=Files.newBufferedReader(dir.resolve("input.properties"))){p.load(reader);}
    var song=new MusicXMLFileReader(new File(p.getProperty("xml"))).readSong();
    song.setName(p.getProperty("title"));song.setTempo(Integer.parseInt(p.getProperty("tempo")));
    var cls=song.getChordLeadSheet();var ss=song.getSongStructure();
    if(ss.getSizeInBars()!=Integer.parseInt(p.getProperty("bars")))throw new Exception("Imported length mismatch: "+ss.getSizeInBars());
    var imported=new ArrayList<String>();
    for(var c:cls.getItems(CLI_ChordSymbol.class))imported.add(c.getPosition().getBar()+"\t"+c.getPosition().getBeat()+"\t"+c.getData().getName());
    Files.write(dir.resolve("raw_import_chords.tsv"),imported);
    // Restore exact fractional source positions instead of the importer's whole-beat rounding.
    for(var c:new ArrayList<>(cls.getItems(CLI_ChordSymbol.class)))cls.removeItem(c);
    for(String line:Files.readAllLines(dir.resolve("chords.tsv"))){var a=line.split("\t");cls.addItem(CLI_Factory.getDefault().createChordSymbol(a[2],Integer.parseInt(a[0]),Float.parseFloat(a[1])));}
    var corrected=new ArrayList<String>();
    for(var c:cls.getItems(CLI_ChordSymbol.class))corrected.add(c.getPosition().getBar()+"\t"+c.getPosition().getBeat()+"\t"+c.getData().getName());
    Files.write(dir.resolve("verified_chords.tsv"),corrected);
    if(p.getProperty("variation").equals("evolving")) {
      var ts=cls.getSection(0).getData().getTimeSignature();
      int bars=Integer.parseInt(p.getProperty("bars"));
      for(int cut:new int[]{bars/2,3*bars/4}){
        boolean present=false;String carry=null;
        for(var c:cls.getItems(CLI_ChordSymbol.class)){
          if(c.getPosition().getBar()<cut || c.getPosition().getBar()==cut && c.getPosition().getBeat()==0)carry=c.getData().getName();
          if(c.getPosition().getBar()==cut && c.getPosition().getBeat()==0)present=true;
        }
        if(!present)cls.addItem(CLI_Factory.getDefault().createChordSymbol(carry,cut,0));
        cls.addSection(CLI_Factory.getDefault().createSection(cut==bars/2?"Development B":"Development C",ts,cut,cls));
      }
    }
    var rhythm=db.getRhythmInstance(p.getProperty("style"));
    ss.setSongPartsRhythm(ss.getSongParts(),rhythm,null);
    int partIndex=0;
    for(var part:ss.getSongParts()){
      var variation=RP_SYS_Variation.getVariationRp(rhythm);
      String variant=p.getProperty("variation");
      int intensity=Integer.parseInt(p.getProperty("intensity"));
      if(variant.equals("evolving")){variant=new String[]{"Main A-1","Main B-1","Main C-1"}[partIndex];intensity=new int[]{-1,0,2}[partIndex];}
      if(variation==null || !variation.getPossibleValues().contains(variant))throw new Exception("Unavailable variation "+variant);
      ss.setRhythmParameterValue(part,variation,variant);
      var intensityRp=RP_SYS_Intensity.getIntensityRp(rhythm);
      if(intensityRp!=null)ss.setRhythmParameterValue(part,intensityRp,intensity);
      var fill=RP_SYS_Fill.getFillRp(rhythm);
      if(fill!=null)ss.setRhythmParameterValue(part,fill,p.getProperty("variation").equals("evolving") && partIndex<2 ? "always" : "");
      partIndex++;
    }
    var melody=new Phrase(0);
    for(String line:Files.readAllLines(dir.resolve("melody.tsv"))){var a=line.split("\t");melody.add(new NoteEvent(Integer.parseInt(a[0]),Float.parseFloat(a[2]),Integer.parseInt(a[3]),Float.parseFloat(a[1])));}
    song.setUserPhrase("Original melody",melody);
    String ensemble=p.getProperty("ensemble");
    song.setUserPhrase("Background line",readPhrase(dir.resolve("upper.tsv"),2));
    if(Files.exists(dir.resolve("triangle.tsv")))song.setUserPhrase(p.getProperty("percussion_name"),readDrumPhrase(dir.resolve("triangle.tsv")));
    if(ensemble.equals("trio") || ensemble.equals("chamber"))song.setUserPhrase("Simple bass",readPhrase(dir.resolve("bass.tsv"),1));
    if(ensemble.equals("chamber"))song.setUserPhrase("Sustained strings",readPhrase(dir.resolve("strings.tsv"),2));
    var mix=MidiMixManager.getDefault().createMix(song);
    var synth=OutputSynthManager.getDefault().getStandardOutputSynth(OutputSynthManager.STD_GM);
    synth.fixInstruments(mix,true);
    for(var rv:mix.getRhythmVoices()){
      var im=mix.getInstrumentMix(rv);im.getSettings().setVolume(rv.isDrums()?42:62);
      im.getSettings().setReverb(0);im.getSettings().setChorus(0);
      boolean keep=!(p.getProperty("replace_beat","false").equals("true") && rv.isDrums() && !rv.getName().equals(p.getProperty("percussion_name")));
      im.setMute(!keep);

    }
    var melodyVoice=mix.getUserRhythmVoice("Original melody");
    var melodyMix=mix.getInstrumentMix(melodyVoice);
    melodyMix.setInstrument(GMSynth.getInstance().getGM1Bank().getInstrument(Integer.parseInt(p.getProperty("lead"))));
    melodyMix.getSettings().setVolume(105);
    var backgroundMix=mix.getInstrumentMix(mix.getUserRhythmVoice("Background line"));
    backgroundMix.setInstrument(GMSynth.getInstance().getGM1Bank().getInstrument(Integer.parseInt(p.getProperty("counter_program"))));
    backgroundMix.getSettings().setVolume(Integer.parseInt(p.getProperty("counter_volume")));
    backgroundMix.getSettings().setPanoramic(74);
    var context=SongContextFactory.getDefault().of(song,mix);
    var builder=new SongSequenceBuilder(context);
    var phrases=new HashMap<>(builder.buildMapRvPhrase(true));
    int zeroVelocities=0;
    for(var entry:phrases.entrySet()){
      zeroVelocities+=(int)entry.getValue().stream().filter(n->n.getVelocity()==0).count();
      entry.setValue(entry.getValue().getProcessedPhraseVelocity(v->Math.max(1,v)));
    }
    Files.writeString(dir.resolve("midi_export_adjustments.txt"),"Zero-velocity generated note-ons clamped to velocity 1 before MIDI serialization: "+zeroVelocities+"\n");
    var sequence=builder.buildSongSequence(phrases);builder.makeSequenceExportable(sequence,false);
    String stem=p.getProperty("filename");
    var midiBytes=new ByteArrayOutputStream();MidiSystem.write(sequence.sequence,1,midiBytes);
    Path tempMidi=dir.resolve(stem+".mid.tmp");Files.write(tempMidi,midiBytes.toByteArray());
    for(int retry=0;;retry++){
      try{Files.move(tempMidi,dir.resolve(stem+".mid"),StandardCopyOption.REPLACE_EXISTING);break;}
      catch(IOException ex){if(retry>=20)throw ex;Thread.sleep(250);}
    }
    song.saveToFile(dir.resolve(stem+".sng").toFile(),false);
    mix.saveToFile(dir.resolve(stem+".mix").toFile(),false);
    Files.writeString(dir.resolve("generation.txt"),"JJazzLab Toolkit 5.2.1\nStyle: "+rhythm.getName()+"\n"+mix.toDebugString()+"\nMelody channel (zero-based): "+mix.getChannel(melodyVoice)+"\n");
    var reopened=org.jjazz.song.spi.SongFactory.getDefault().loadFromFile(dir.resolve(stem+".sng").toFile());
    if(reopened.getUserPhrase("Original melody").size()!=melody.size() || reopened.getChordLeadSheet().getItems(CLI_ChordSymbol.class).size()!=cls.getItems(CLI_ChordSymbol.class).size())throw new Exception("Native project reload mismatch");
    Files.writeString(dir.resolve("native_reload_verified.txt"),"Saved project reopened successfully: original melody and chord counts match.\n");
    StringBuilder trackManifest=new StringBuilder("channel\tvoice\tprogram\tvolume\tpan\tmuted\n");
    for(var voice:mix.getRhythmVoices()){
      var im=mix.getInstrumentMix(voice);trackManifest.append(mix.getChannel(voice)).append("\t").append(voice.getName()).append("\t").append(im.getInstrument().getMidiAddress().getProgramChange()).append("\t").append(im.getSettings().getVolume()).append("\t").append(im.getSettings().getPanoramic()).append("\t").append(im.isMute()).append("\n");
    }
    Files.writeString(dir.resolve("tracks.tsv"),trackManifest.toString());
    System.out.println("EXPORTED "+dir);
  }
  static Phrase readDrumPhrase(Path file)throws Exception {
    var result=new Phrase(9,true);
    for(var line:Files.readAllLines(file)){var a=line.split("\t");result.add(new NoteEvent(Integer.parseInt(a[0]),Float.parseFloat(a[2]),Integer.parseInt(a[3]),Float.parseFloat(a[1])));}
    return result;
  }
  static Phrase readPhrase(Path file,int channel)throws Exception {
    var result=new Phrase(channel);
    for(var line:Files.readAllLines(file)){var a=line.split("\t");result.add(new NoteEvent(Integer.parseInt(a[0]),Float.parseFloat(a[2]),Integer.parseInt(a[3]),Float.parseFloat(a[1])));}
    return result;
  }
}
