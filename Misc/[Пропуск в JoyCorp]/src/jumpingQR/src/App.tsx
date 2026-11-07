import Lanyard from "./components/Lanyard";
import "./App.css";

function App() {
  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        backgroundImage: "url('/bg.png')",
        backgroundSize: "contain",
        backgroundPosition: "center",
        backgroundRepeat: "no-repeat"
      }}
    >
      <Lanyard />
    </div>
  );
}

export default App;
